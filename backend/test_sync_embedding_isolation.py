"""
Locks in the fix for a real production crash: a rate-limited (429)
embedding API call inside /api/vault/sync used to crash the ENTIRE
sync -- documents, facts, events, everything -- because embeddings
ran unconditionally inside the main sync loop.

Embeddings are now computed lazily, only when semantic checking is
actually invoked (opt-in, same pattern as LLM extraction). This test
proves sync succeeds even when the configured embedding provider
raises on every call.

Run with:
    python test_sync_embedding_isolation.py
"""

import datetime
import os
import shutil
from pathlib import Path

os.environ.setdefault("DATABASE_PASSWORD", "x")
os.environ.setdefault("OBSIDIAN_VAULT_PATH", "/tmp/loreguard_isolation_vault")

VAULT = Path("/tmp/loreguard_isolation_vault")
if VAULT.exists():
    shutil.rmtree(VAULT)
VAULT.mkdir(parents=True)

(VAULT / "Lunaris.md").write_text(
    "---\ntags: [bóg]\ntytul: Księżycowa Dama\n---\n"
    "Lunaris jest boginią księżyca.\n",
    encoding="utf-8",
)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.database import Base, get_db
from app.services.embedding_provider import EmbeddingProvider
import app.main as main_module

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(test_engine)
TestSession = sessionmaker(bind=test_engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


main_module.app.dependency_overrides[get_db] = override_get_db

client = TestClient(main_module.app)

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  OK   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}")


class AlwaysFailingEmbeddingProvider(EmbeddingProvider):
    """Simulates a 429 RESOURCE_EXHAUSTED on every single call."""

    dimensions = 8

    def embed(self, text: str):
        raise RuntimeError(
            "429 RESOURCE_EXHAUSTED: quota exceeded (simulated)"
        )


# Patch the factory so EVERY embedding-provider lookup in the app
# returns something that always raises -- worst case scenario.
main_module.get_embedding_provider = lambda settings: AlwaysFailingEmbeddingProvider()

print("=" * 60)
print("POST /api/vault/sync must succeed even if the embedding")
print("           provider fails on every call")
print("=" * 60)

r = client.post("/api/vault/sync")
check("status 200, NOT a 500 crash", r.status_code == 200)

body = r.json()
check("document was actually synced", body.get("documents_synced") == 1)
check("facts were extracted normally", body["documents"][0]["facts_extracted"] >= 1)

r2 = client.get("/api/documents")
check("document is queryable afterwards", r2.json()["total"] == 1)

r3 = client.get("/api/dashboard")
check("dashboard works normally", r3.status_code == 200 and r3.json()["documents"] == 1)

print()
print("=" * 60)
print("Per-document semantic check fails gracefully (JSON error,")
print("           not a raw 500) when the embedding provider fails")
print("=" * 60)

doc_id = client.get("/api/documents").json()["items"][0]["id"]

# get_llm_provider also needs to be non-None for this code path to
# reach the embedding call at all.
from app.services.llm_provider import LLMProvider

class DummyLLM(LLMProvider):
    def extract_facts(self, text, known_entity_names):
        return []
    def compare_texts(self, *a, **kw):
        return []

main_module.get_llm_provider = lambda settings: DummyLLM()

r4 = client.post(f"/api/documents/{doc_id}/check-semantic-conflicts")
check("status 200, NOT a raw 500", r4.status_code == 200)
check("clean JSON error returned", "error" in r4.json())
print("  error message:", r4.json().get("error"))

print()
print("=" * 60)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 60)

if failed:
    raise SystemExit(1)
