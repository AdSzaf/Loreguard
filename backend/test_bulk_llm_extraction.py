"""
Full end-to-end test of POST /api/vault/extract-llm-facts through
the real FastAPI app (TestClient + in-memory SQLite), with
app.main.get_llm_provider patched to a fake provider -- no real
network/API key needed.

Run with:
    python test_bulk_llm_extraction.py
"""

import datetime
import os
import shutil
from pathlib import Path

os.environ.setdefault("DATABASE_PASSWORD", "x")
os.environ.setdefault("OBSIDIAN_VAULT_PATH", "/tmp/loreguard_bulk_e2e_vault")

VAULT = Path("/tmp/loreguard_bulk_e2e_vault")
if VAULT.exists():
    shutil.rmtree(VAULT)
VAULT.mkdir(parents=True)

(VAULT / "Lunaris.md").write_text(
    "---\ntags: [bóg]\n---\nLunaris jest boginią księżyca.\n",
    encoding="utf-8",
)
(VAULT / "Tranio.md").write_text(
    "---\ntags: [Postać]\n---\nTranio był żeglarzem.\n",
    encoding="utf-8",
)
(VAULT / "Broken.md").write_text(
    "---\ntags: [Postać]\n---\nTen dokument spowoduje błąd LLM.\n",
    encoding="utf-8",
)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.database import Base, get_db
from app.services.llm_provider import ExtractedFact, LLMProvider
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


class FakeBulkProvider(LLMProvider):
    """Fails on any text mentioning 'błąd', succeeds otherwise."""

    def extract_facts(self, text, known_entity_names):
        if "błąd" in text:
            raise RuntimeError("simulated LLM failure")

        return [
            ExtractedFact(
                subject=known_entity_names[0] if known_entity_names else "X",
                predicate="opisany",
                object="tak",
                confidence=0.7,
                source_text=text[:30],
            )
        ]


fake_provider_instance = FakeBulkProvider()
main_module.get_llm_provider = lambda settings: fake_provider_instance

print("=" * 60)
print("Setup: sync the vault first (frontmatter facts/entities)")
print("=" * 60)
r = client.post("/api/vault/sync")
check("sync succeeded", r.status_code == 200)

docs_before = client.get("/api/documents").json()
check("3 documents exist", len(docs_before) == 3)
check(
    "all 3 need LLM processing initially",
    all(d["needs_llm_processing"] for d in docs_before),
)

print()
print("=" * 60)
print("First bulk run: 2 succeed, 1 fails, none skipped")
print("=" * 60)
r = client.post("/api/vault/extract-llm-facts")
check("status 200", r.status_code == 200)
body = r.json()
print("  response:", body)

check("documents_total == 3", body["documents_total"] == 3)
check("processed == 2 (Lunaris, Tranio)", body["processed"] == 2)
check("skipped_up_to_date == 0 (first run)", body["skipped_up_to_date"] == 0)
check("exactly 1 failure recorded", len(body["failed"]) == 1)
check("failure is about 'Broken'", body["failed"][0]["document"] == "Broken")
check(
    "failure message is surfaced, not swallowed",
    "simulated LLM failure" in body["failed"][0]["error"],
)

print()
print("=" * 60)
print("Second bulk run: succeeded docs are skipped, failed one retried")
print("=" * 60)
r = client.post("/api/vault/extract-llm-facts")
body2 = r.json()
print("  response:", body2)

check(
    "the 2 successful docs are now skipped (already up to date)",
    body2["skipped_up_to_date"] == 2,
)
check(
    "the failed doc is retried, not silently skipped",
    body2["processed"] == 0 and len(body2["failed"]) == 1,
)

docs_after = client.get("/api/documents").json()
lunaris = next(d for d in docs_after if d["title"] == "Lunaris")
broken = next(d for d in docs_after if d["title"] == "Broken")
check("Lunaris no longer needs LLM processing", not lunaris["needs_llm_processing"])
check("Broken still needs processing (it failed)", broken["needs_llm_processing"])

print()
print("=" * 60)
print("force=true reprocesses everything regardless of hash")
print("=" * 60)
r = client.post("/api/vault/extract-llm-facts?force=true")
body3 = r.json()
check(
    "force=true attempts all 3 again (2 processed + 1 still fails)",
    body3["processed"] == 2 and len(body3["failed"]) == 1,
)
check("nothing skipped when forced", body3["skipped_up_to_date"] == 0)

print()
print("=" * 60)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 60)

if failed:
    raise SystemExit(1)
