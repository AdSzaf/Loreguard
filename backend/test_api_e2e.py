"""
Full end-to-end smoke test: hits the actual FastAPI app through
every /api/* endpoint, backed by in-memory SQLite instead of
Postgres. Not a permanent project file -- just used to verify
main.py works before handing it off.
"""

import datetime
import os

os.environ.setdefault("DATABASE_PASSWORD", "x")
os.environ.setdefault("OBSIDIAN_VAULT_PATH", "/tmp/loreguard_e2e_vault")

import shutil
from pathlib import Path

VAULT = Path("/tmp/loreguard_e2e_vault")
if VAULT.exists():
    shutil.rmtree(VAULT)
VAULT.mkdir(parents=True)

(VAULT / "Lunaris.md").write_text(
    "---\n"
    "tags: [bóg]\n"
    "tytul: Księżycowa Dama\n"
    "---\n"
    "Lunaris jest boginią księżyca.\n",
    encoding="utf-8",
)

(VAULT / "Bitwa_pod_Arven.md").write_text(
    "---\n"
    "tags: [bitwa]\n"
    "data: wiosna 842\n"
    "wynik: Zwycięstwo Valdoru\n"
    "---\n"
    "Bitwa pod Arven.\n",
    encoding="utf-8",
)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.database import Base, get_db
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


print("=" * 60)
print("GET /")
print("=" * 60)
r = client.get("/")
check("status 200", r.status_code == 200)
check("has application name", "application" in r.json())

print()
print("=" * 60)
print("GET /api/health")
print("=" * 60)
r = client.get("/api/health")
check("status 200", r.status_code == 200)

print()
print("=" * 60)
print("GET /api/vault/scan")
print("=" * 60)
r = client.get("/api/vault/scan")
check("status 200", r.status_code == 200)
check("finds 2 files", r.json()["files_found"] == 2)

print()
print("=" * 60)
print("POST /api/vault/sync")
print("=" * 60)
r = client.post("/api/vault/sync")
check("status 200", r.status_code == 200)
body = r.json()
check("2 documents synced", body["documents_synced"] == 2)
check("conflicts key present", "conflicts" in body)
print("  response:", body)

print()
print("=" * 60)
print("GET /api/documents (paginated)")
print("=" * 60)
r = client.get("/api/documents")
check("status 200", r.status_code == 200)
docs_body = r.json()
check("has pagination envelope", {"items", "total", "page", "page_size", "total_pages"} <= docs_body.keys())
check("2 documents listed", len(docs_body["items"]) == 2)
check("total == 2", docs_body["total"] == 2)
check(
    "sorted alphabetically by title",
    [d["title"] for d in docs_body["items"]] == sorted(d["title"] for d in docs_body["items"]),
)

r = client.get("/api/documents?page=1&page_size=1")
check("page_size=1 returns exactly 1 item", len(r.json()["items"]) == 1)
check("total_pages == 2 with page_size=1", r.json()["total_pages"] == 2)

print()
print("=" * 60)
print("GET /api/documents/{id} (detail)")
print("=" * 60)
doc_id_for_detail = docs_body["items"][0]["id"]
r = client.get(f"/api/documents/{doc_id_for_detail}")
check("status 200", r.status_code == 200)
doc_detail = r.json()
check("has facts key", "facts" in doc_detail)
check("has entities key", "entities" in doc_detail)

print()
print("=" * 60)
print("GET /api/entities (paginated)")
print("=" * 60)
r = client.get("/api/entities")
check("status 200", r.status_code == 200)
entities_body = r.json()
check("has pagination envelope", {"items", "total", "page", "page_size", "total_pages"} <= entities_body.keys())
entities = entities_body["items"]
check("Lunaris entity exists", any(e["name"] == "Lunaris" for e in entities))
lunaris = next(e for e in entities if e["name"] == "Lunaris")
check("Lunaris typed as deity", lunaris["entity_type"] == "deity")
check(
    "sorted alphabetically by name",
    [e["name"] for e in entities] == sorted(e["name"] for e in entities),
)

print()
print("=" * 60)
print("GET /api/entities/{id}")
print("=" * 60)
r = client.get(f"/api/entities/{lunaris['id']}")
check("status 200", r.status_code == 200)
detail = r.json()
check("has facts key", "facts" in detail)
check("tytul fact present", any(f["predicate"] == "tytul" for f in detail["facts"]))

print()
print("=" * 60)
print("GET /api/documents/{id}/similar")
print("=" * 60)
r = client.get(f"/api/documents/{lunaris['id']}/similar")
check("status 200", r.status_code == 200)
similar_body = r.json()
check("has 'similar' key", "similar" in similar_body)
print("  response:", similar_body)
print("=" * 60)
r = client.get("/api/facts")
check("status 200", r.status_code == 200)
check("at least 1 fact", len(r.json()) >= 1)

r = client.get(f"/api/facts?entity_id={lunaris['id']}")
check("filter by entity_id works", all(f["subject"] == "Lunaris" for f in r.json()))

print()
print("=" * 60)
print("GET /api/events")
print("=" * 60)
r = client.get("/api/events")
check("status 200", r.status_code == 200)
events = r.json()
check("1 event found", len(events) == 1)
check("event date parsed to 842", events[0]["date_start_year"] == 842)

print()
print("=" * 60)
print("GET /api/conflicts")
print("=" * 60)
r = client.get("/api/conflicts")
check("status 200", r.status_code == 200)
check("0 conflicts on clean vault", len(r.json()) == 0)

r = client.get("/api/conflicts?status=open")
check("status filter works, still 0", len(r.json()) == 0)

print()
print("=" * 60)
print("GET /api/llm/status (no keys set)")
print("=" * 60)
r = client.get("/api/llm/status")
check("status 200", r.status_code == 200)
check("no active provider", r.json()["active_provider"] is None)

print()
print("=" * 60)
print("POST /api/documents/{id}/extract-llm-facts (no API key set)")
print("=" * 60)
lunaris_doc_id = next(d["id"] for d in client.get("/api/documents").json()["items"] if d["title"] == "Lunaris")
r = client.post(f"/api/documents/{lunaris_doc_id}/extract-llm-facts")
check("status 200 (graceful, not a crash)", r.status_code == 200)
check("clear error message about missing API key", "GEMINI_API_KEY" in r.json().get("error", "") or "ANTHROPIC_API_KEY" in r.json().get("error", ""))

print()
print("=" * 60)
print("GET /api/dashboard")
print("=" * 60)
r = client.get("/api/dashboard")
check("status 200", r.status_code == 200)
dash = r.json()
check("documents count = 2", dash["documents"] == 2)
check("canon health 100% (no conflicts)", dash["canon_health_percent"] == 100.0)
print("  dashboard:", dash)

print()
print("=" * 60)
print("Re-sync is idempotent through the real API")
print("=" * 60)
r = client.post("/api/vault/sync")
body2 = r.json()
check("still 2 documents after re-sync", body2["documents_synced"] == 2)

r = client.get("/api/facts")
check(
    "fact count unchanged after re-sync (no duplication)",
    len(r.json()) == len(client.get("/api/facts").json()),
)

r = client.get("/api/entities")
check("entity count unchanged after re-sync", r.json()["total"] == entities_body["total"])

print()
print("=" * 60)
print("POST /api/vault/sync — deleted file removed from DB")
print("=" * 60)
import os as _os
(VAULT / "Bitwa_pod_Arven.md").unlink()
r = client.post("/api/vault/sync")
body3 = r.json()
check("files_found dropped to 1", body3["files_found"] == 1)
check("documents_deleted == 1", body3["documents_deleted"] == 1)
r = client.get("/api/documents")
check("only 1 document remains", r.json()["total"] == 1)
check("the remaining one is Lunaris", r.json()["items"][0]["title"] == "Lunaris")

print()
print("=" * 60)
print("POST /api/vault/sync — empty scan does NOT wipe the DB")
print("=" * 60)
import shutil as _shutil
remaining_files = list(VAULT.glob("*.md"))
_holding_dir = VAULT.parent / "loreguard_e2e_vault_holding"
_holding_dir.mkdir(exist_ok=True)
for f in remaining_files:
    _shutil.move(str(f), str(_holding_dir / f.name))
r = client.post("/api/vault/sync")
body4 = r.json()
check("files_found == 0", body4["files_found"] == 0)
check("documents_deleted == 0 (safety guard)", body4["documents_deleted"] == 0)
r = client.get("/api/documents")
check("Lunaris still exists (nothing was wiped)", r.json()["total"] == 1)
for f in _holding_dir.glob("*.md"):
    _shutil.move(str(f), str(VAULT / f.name))

print()
print("=" * 60)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 60)

if failed:
    raise SystemExit(1)
