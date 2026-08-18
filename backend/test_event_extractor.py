"""
Self-contained test for the entity-type/event extraction pipeline.

Unlike test_fact_extractor.py / test_entity_indexer.py, this does
NOT touch your real Postgres vault. It spins up an in-memory
SQLite database and feeds it frontmatter shaped exactly like real
LoreGuard notes (Polish field names, no English keywords at all),
so it can run anytime without needing a synced vault.

Run with:
    python test_event_extractor.py
"""

import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.vault_schema import VaultSchema
from app.models import Document, Entity, EntityType, Event
from app.services.entity_indexer import EntityIndexer
from app.services.event_extractor import EventExtractor
from app.services.fact_extractor import FactExtractor
from app.schemas.document import ParsedDocument


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


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # No .loreguard/schema.yaml on this path -> built-in defaults only.
    schema = VaultSchema(Path("/tmp/loreguard_test_vault_does_not_exist"))

    entity_indexer = EntityIndexer(db, schema)
    fact_extractor = FactExtractor(db)
    event_extractor = EventExtractor(db, schema)

    now = datetime.datetime.utcnow()

    # --- Case 1: standalone deity note, nothing links to it yet ---

    print("=" * 60)
    print("CASE 1: Lunaris (bóg) -- no incoming links")
    print("=" * 60)

    lunaris_frontmatter = {
        "aliases": ["Lunaris", "Lunarisie", "Lunariso", "Lunarisy"],
        "tags": ["bóg"],
        "kategoria_pochodzenia": "Bóstwo Domenowe",
        "tytul": "Księżycowa Dama",
        "domena": "Noc, księżyc, fazy księżyca",
    }

    lunaris_doc = Document(
        title="Lunaris",
        path="Bogowie/Lunaris.md",
        content="Lunaris jest boginią księżyca.",
        content_hash="lunaris-1",
        file_modified_at=now,
    )
    db.add(lunaris_doc)
    db.flush()

    entity_indexer.index_document(lunaris_doc, lunaris_frontmatter)
    db.commit()

    lunaris_entity = next(
        (e for e in lunaris_doc.entities if e.name == "Lunaris"), None
    )

    check(
        "subject entity was created despite no incoming wikilinks",
        lunaris_entity is not None,
    )
    check(
        "entity_type resolved from tags=['bóg'] -> DEITY",
        lunaris_entity is not None
        and lunaris_entity.entity_type == EntityType.DEITY,
    )

    lunaris_parsed = ParsedDocument(
        title=lunaris_doc.title,
        path=lunaris_doc.path,
        content=lunaris_doc.content,
        content_hash=lunaris_doc.content_hash,
        file_modified_at=now,
        frontmatter=lunaris_frontmatter,
    )

    lunaris_facts = fact_extractor.extract_from_document(
        lunaris_doc, lunaris_parsed
    )
    db.commit()

    check(
        "custom Polish frontmatter fields became Facts (3 expected)",
        len(lunaris_facts) == 3,
    )

    lunaris_event = event_extractor.extract_from_document(
        lunaris_doc, lunaris_parsed
    )

    check(
        "Lunaris (no date field, no event tag) is NOT an Event",
        lunaris_event is None,
    )

    # --- Case 2: a country note with almost no frontmatter ---

    print()
    print("=" * 60)
    print("CASE 2: Magnia (Kraj) -- minimal frontmatter")
    print("=" * 60)

    magnia_frontmatter = {
        "aliases": ["Magnii", "Magnię", "Magnią", "Magnio"],
        "tags": ["Kraj"],
    }

    magnia_doc = Document(
        title="Magnia",
        path="Krainy/Magnia.md",
        content="Właściwie Boskie królestwo Magnii.",
        content_hash="magnia-1",
        file_modified_at=now,
    )
    db.add(magnia_doc)
    db.flush()

    entity_indexer.index_document(magnia_doc, magnia_frontmatter)
    db.commit()

    magnia_entity = next(
        (e for e in magnia_doc.entities if e.name == "Magnia"), None
    )

    check(
        "entity_type resolved from tags=['Kraj'] -> COUNTRY",
        magnia_entity is not None
        and magnia_entity.entity_type == EntityType.COUNTRY,
    )

    # --- Case 3: event note using only Polish field names ---

    print()
    print("=" * 60)
    print("CASE 3: Bitwa pod Arven -- Polish-only event fields")
    print("=" * 60)

    for name, etype in [
        ("Arven", EntityType.PLACE),
        ("Valdor", EntityType.COUNTRY),
        ("Aldren II", EntityType.PERSON),
    ]:
        db.add(Entity(name=name, entity_type=etype))
    db.commit()

    battle_frontmatter = {
        "tags": ["bitwa"],
        "data": "wiosna 842",
        "lokalizacja": "[[Arven]]",
        "uczestnicy": ["[[Valdor]]"],
        "dowódca": ["[[Aldren II]]"],
        "wynik": "Zwycięstwo Valdoru",
    }

    battle_doc = Document(
        title="Bitwa pod Arven",
        path="Historia/Bitwa_pod_Arven.md",
        content="",
        content_hash="battle-1",
        file_modified_at=now,
    )
    db.add(battle_doc)
    db.commit()

    entity_indexer.index_document(battle_doc, battle_frontmatter)
    db.commit()

    battle_parsed = ParsedDocument(
        title=battle_doc.title,
        path=battle_doc.path,
        content="",
        content_hash=battle_doc.content_hash,
        file_modified_at=now,
        frontmatter=battle_frontmatter,
    )

    battle_event = event_extractor.extract_from_document(
        battle_doc, battle_parsed
    )
    db.commit()

    check(
        "tags=['bitwa'] + 'data' field -> recognised as an Event",
        battle_event is not None,
    )
    check(
        "'wiosna 842' parsed to year 842",
        battle_event is not None and battle_event.date_start_year == 842,
    )
    check(
        "'lokalizacja: [[Arven]]' resolved to the Arven entity",
        battle_event is not None
        and battle_event.location is not None
        and battle_event.location.name == "Arven",
    )
    check(
        "'wynik' mapped to outcome",
        battle_event is not None
        and battle_event.outcome == "Zwycięstwo Valdoru",
    )

    participant_names = (
        {p.entity.name for p in battle_event.participants}
        if battle_event
        else set()
    )
    commander_names = (
        {
            p.entity.name
            for p in battle_event.participants
            if p.role == "commander"
        }
        if battle_event
        else set()
    )

    check(
        "'uczestnicy' -> Valdor listed as participant",
        "Valdor" in participant_names,
    )
    check(
        "'dowódca' -> Aldren II listed with role='commander'",
        "Aldren II" in commander_names,
    )

    # --- Case 4: editing the note removes a participant ---

    print()
    print("=" * 60)
    print("CASE 4: re-sync after removing the commander field")
    print("=" * 60)

    battle_frontmatter_v2 = dict(battle_frontmatter)
    battle_frontmatter_v2["dowódca"] = []

    battle_parsed_v2 = battle_parsed.model_copy(
        update={"frontmatter": battle_frontmatter_v2}
    )

    battle_event_v2 = event_extractor.extract_from_document(
        battle_doc, battle_parsed_v2
    )
    db.commit()

    commander_names_v2 = {
        p.entity.name
        for p in battle_event_v2.participants
        if p.role == "commander"
    }

    check(
        "commander removed from frontmatter -> removed from participants",
        "Aldren II" not in commander_names_v2,
    )
    check(
        "other participants untouched by the re-sync",
        "Valdor" in {p.entity.name for p in battle_event_v2.participants},
    )

    check(
        "exactly one Event row exists for the battle (no duplicates)",
        db.query(Event).filter(Event.entity_id == battle_event.entity_id)
        .count() == 1,
    )

    print()
    print("=" * 60)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 60)

    db.close()

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
