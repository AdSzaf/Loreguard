import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.core.database import Base, get_db
from app.core.vault_schema import VaultSchema
from app.models import Document, Entity, EntityType
from app.services.entity_indexer import EntityIndexer
from app.services.event_extractor import EventExtractor
from app.services.fact_extractor import FactExtractor
from app.services.consistency_engine import ConsistencyEngine
from app.schemas.document import ParsedDocument

import app.main as main_module

passed = 0
failed = 0


def check(label: str, condition: bool) -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  OK   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}")


from sqlalchemy.pool import StaticPool

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # Utrzymuje to samo połączenie w pamięci dla wszystkich sesji
)
Base.metadata.create_all(engine)
TestSession = sessionmaker(bind=engine)

_session = TestSession()


def override_get_db():
    try:
        yield _session
    finally:
        pass


main_module.app.dependency_overrides[get_db] = override_get_db
client = TestClient(main_module.app)

# --- seed data directly (bypassing filesystem scan) ---

schema = VaultSchema(Path("/tmp/loreguard_test_vault_does_not_exist"))
entity_indexer = EntityIndexer(_session, schema)
fact_extractor = FactExtractor(_session)
event_extractor = EventExtractor(_session, schema)

now = datetime.datetime.utcnow()

lunaris_fm = {"tags": ["bóg"], "tytul": "Księżycowa Dama"}
lunaris_doc = Document(
    title="Lunaris", path="Bogowie/Lunaris.md", content="",
    content_hash="l1", file_modified_at=now,
)
_session.add(lunaris_doc)
_session.flush()
entity_indexer.index_document(lunaris_doc, lunaris_fm)
_session.commit()
fact_extractor.extract_from_document(
    lunaris_doc,
    ParsedDocument(
        title="Lunaris", path=lunaris_doc.path, content="",
        content_hash="l1", file_modified_at=now, frontmatter=lunaris_fm,
    ),
)
_session.commit()

battle_fm = {
    "tags": ["bitwa"], "data": "842", "lokalizacja": "[[Arven]]",
    "uczestnicy": ["[[Valdor]]"],
}
_session.add(Entity(name="Arven", entity_type=EntityType.PLACE))
_session.add(Entity(name="Valdor", entity_type=EntityType.COUNTRY))
_session.commit()

battle_doc = Document(
    title="Bitwa pod Arven", path="Historia/Bitwa.md", content="",
    content_hash="b1", file_modified_at=now,
)
_session.add(battle_doc)
_session.flush()
entity_indexer.index_document(battle_doc, battle_fm)
_session.commit()
battle_parsed = ParsedDocument(
    title="Bitwa pod Arven", path=battle_doc.path, content="",
    content_hash="b1", file_modified_at=now, frontmatter=battle_fm,
)
event_extractor.extract_from_document(battle_doc, battle_parsed)
_session.commit()

# conflicting fact to make sure /api/conflicts has something to show
from app.models import Fact

lunaris_entity = next(e for e in lunaris_doc.entities if e.name == "Lunaris")
_session.add(
    Fact(
        subject_entity_id=lunaris_entity.id,
        predicate="tytul",
        object_value="Pani Nocy",
        document_id=lunaris_doc.id,
    )
)
_session.commit()

ConsistencyEngine(_session, schema=schema).run()
_session.commit()

# --- now hit every endpoint ---

print("=" * 60)
print("Endpoint smoke test")
print("=" * 60)

r = client.get("/api/dashboard")
check("GET /api/dashboard -> 200", r.status_code == 200)
body = r.json()
check("dashboard documents count == 2", body.get("documents") == 2)
check("dashboard entities count >= 3", body.get("entities", 0) >= 3)
check("dashboard has at least 1 open conflict", body.get("conflicts_open", 0) >= 1)
check(
    "canon_health_percent is a number between 0 and 100",
    isinstance(body.get("canon_health_percent"), (int, float))
    and 0 <= body["canon_health_percent"] <= 100,
)

r = client.get("/api/documents")
check("GET /api/documents -> 200", r.status_code == 200)
check("2 documents listed", len(r.json()) == 2)

r = client.get("/api/entities")
check("GET /api/entities -> 200", r.status_code == 200)
entities = r.json()
check("Lunaris entity present with type DEITY", any(
    e["name"] == "Lunaris" and "DEITY" in str(e["entity_type"]).upper()
    for e in entities
))
r = client.get("/api/entities?entity_type=EntityType.PLACE")
# entity_type stored as python Enum repr via string(); accept either shape
r2 = client.get(f"/api/entities/{lunaris_entity.id}")
check("GET /api/entities/{id} -> 200", r2.status_code == 200)
detail = r2.json()
check("entity detail includes its facts", len(detail.get("facts", [])) >= 1)
check("entity detail includes its conflicts", len(detail.get("conflicts", [])) >= 1)

r = client.get("/api/facts")
check("GET /api/facts -> 200", r.status_code == 200)
check("at least 2 facts listed (tytul x2)", len(r.json()) >= 2)

r = client.get(f"/api/facts?entity_id={lunaris_entity.id}")
check("GET /api/facts?entity_id filters correctly", all(
    f["subject"] == "Lunaris" for f in r.json()
))

r = client.get("/api/events")
check("GET /api/events -> 200", r.status_code == 200)
events = r.json()
check("battle event present with year 842", any(
    e["name"] == "Bitwa pod Arven" and e["date_start_year"] == 842
    for e in events
))

r = client.get("/api/conflicts")
check("GET /api/conflicts -> 200", r.status_code == 200)
conflicts = r.json()
check("at least 1 conflict returned", len(conflicts) >= 1)
conflict_id = conflicts[0]["id"]

r = client.get("/api/conflicts?status=open")
check("GET /api/conflicts?status=open filters correctly", all(
    "OPEN" in str(c["status"]).upper() for c in r.json()
))

r = client.post(
    f"/api/conflicts/{conflict_id}/resolve",
    params={"status": "dismissed", "resolution_note": "test note"},
)
check("POST /api/conflicts/{id}/resolve -> 200", r.status_code == 200)
check("resolve response reflects new status", "DISMISSED" in str(r.json()["status"]).upper())

r = client.get("/api/conflicts?status=open")
check(
    "resolved conflict no longer shows under status=open",
    all(c["id"] != conflict_id for c in r.json()),
)

print()
print("=" * 60)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 60)

if failed:
    raise SystemExit(1)
