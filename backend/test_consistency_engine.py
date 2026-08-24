"""
Self-contained test for ConsistencyEngine / rules.

In-memory SQLite, no real Postgres/vault needed.

Run with:
    python test_consistency_engine.py
"""

import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.vault_schema import VaultSchema
from app.models import (
    Conflict,
    ConflictStatus,
    Document,
    Entity,
    EntityType,
)
from app.services.consistency_engine import ConsistencyEngine
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


def sync_document(
    entity_indexer,
    fact_extractor,
    event_extractor,
    title,
    path,
    frontmatter,
    content,
    now,
):
    doc = Document(
        title=title,
        path=path,
        content=content,
        content_hash=path,
        file_modified_at=now,
    )
    entity_indexer.db.add(doc)
    entity_indexer.db.flush()

    entity_indexer.index_document(doc, frontmatter)

    parsed = ParsedDocument(
        title=title,
        path=path,
        content=content,
        content_hash=path,
        file_modified_at=now,
        frontmatter=frontmatter,
    )

    fact_extractor.extract_from_document(doc, parsed)
    event_extractor.extract_from_document(doc, parsed)

    return doc


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    schema = VaultSchema(Path("/tmp/loreguard_test_vault_does_not_exist"))
    entity_indexer = EntityIndexer(db, schema)
    fact_extractor = FactExtractor(db)
    event_extractor = EventExtractor(db, schema)

    now = datetime.datetime.utcnow()

    # --- Negative test: real-shaped notes should NOT conflict ---

    print("=" * 60)
    print("CASE 1: real-shaped notes (pantheon-only vault)")
    print("=" * 60)

    sync_document(
        entity_indexer, fact_extractor, event_extractor,
        "Lunaris", "Bogowie/Lunaris.md",
        {
            "tags": ["bóg"],
            "kategoria_pochodzenia": "Bóstwo Domenowe",
            "tytul": "Księżycowa Dama",
        },
        "Lunaris jest boginią księżyca.",
        now,
    )

    sync_document(
        entity_indexer, fact_extractor, event_extractor,
        "Tranio Zorish", "Postacie/Tranio_Zorish.md",
        {
            "tags": ["Postać"],
            "panstwo": "Lusilia",
            "rasa": "Człowiek",
        },
        "Podróżnik i kartograf.",
        now,
    )

    sync_document(
        entity_indexer, fact_extractor, event_extractor,
        "Magnia", "Krainy/Magnia.md",
        {"tags": ["Kraj"]},
        "Właściwie Boskie królestwo Magnii.",
        now,
    )

    db.commit()

    engine_run_1 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check(
        "no false-positive conflicts on real-shaped, non-conflicting notes",
        engine_run_1["created"] == 0,
    )
    check(
        "no Conflict rows exist in the DB at all",
        db.query(Conflict).count() == 0,
    )

    # --- Positive test: same entity, two documents, conflicting fact ---

    print()
    print("=" * 60)
    print("CASE 2: two sources disagree about the same character")
    print("=" * 60)

    # First source: character's own page
    doc_a = sync_document(
        entity_indexer, fact_extractor, event_extractor,
        "Aldren II", "Postacie/Aldren_II.md",
        {"tags": ["Postać"], "rasa": "Człowiek"},
        "",
        now,
    )
    db.commit()

    # Second "source": simulate a different document also claiming
    # to be the subject entity's own page by matching name/alias
    # (mirrors what a duplicate/legend-vs-history article would look
    # like once prose extraction attaches facts to the same entity).
    #
    # Uses "umarł" (canonicalizes to "died"), one of the small
    # default set of predicates ExclusiveFactRule actually treats
    # as single-valued -- "rasa" deliberately is NOT anymore (see
    # DEFAULT_EXCLUSIVE_PREDICATES's docstring): most descriptive
    # predicates are legitimately multi-valued, only a few (died,
    # born, capital) genuinely have one correct answer.
    aldren_entity = next(
        e for e in doc_a.entities if e.name == "Aldren II"
    )

    from app.models import Fact

    db.add(
        Fact(
            subject_entity_id=aldren_entity.id,
            predicate="umarł",
            object_value="842",
            document_id=doc_a.id,
        )
    )
    db.commit()

    conflicting_fact = Fact(
        subject_entity_id=aldren_entity.id,
        predicate="zmarł",
        object_value="857",
        document_id=doc_a.id,
    )
    db.add(conflicting_fact)
    db.commit()

    result_2 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check(
        "conflicting death years detected as a new conflict",
        result_2["created"] == 1,
    )

    check(
        "'rasa' conflicts are NOT auto-flagged anymore (not exclusive by default)",
        result_2["candidates_found"] == 1,
    )

    conflict = db.query(Conflict).filter(
        Conflict.rule_name == "exclusive_fact"
    ).first()

    check(
        "conflict references the correct entity",
        conflict is not None and conflict.entity.name == "Aldren II",
    )
    check(
        "conflict starts in OPEN status",
        conflict is not None and conflict.status == ConflictStatus.OPEN,
    )

    # --- Idempotency: re-running must not duplicate the conflict ---

    print()
    print("=" * 60)
    print("CASE 3: re-running the engine is idempotent")
    print("=" * 60)

    result_3 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check(
        "re-run finds the same candidate but creates nothing new",
        result_3["created"] == 0 and result_3["skipped_existing"] == 1,
    )
    check(
        "still exactly one Conflict row for this pair",
        db.query(Conflict).filter(
            Conflict.rule_name == "exclusive_fact"
        ).count() == 1,
    )

    # --- User decisions must survive future syncs ---

    print()
    print("=" * 60)
    print("CASE 4: a dismissed conflict stays dismissed")
    print("=" * 60)

    conflict.status = ConflictStatus.DISMISSED
    conflict.resolution_note = "To celowa niespójność legendy vs historii."
    db.commit()

    result_4 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    db.refresh(conflict)

    check(
        "engine does not recreate a dismissed conflict",
        result_4["created"] == 0,
    )
    check(
        "conflict status remains DISMISSED after re-run",
        conflict.status == ConflictStatus.DISMISSED,
    )
    check(
        "resolution note is preserved",
        conflict.resolution_note is not None
        and "legendy" in conflict.resolution_note,
    )

    # --- Event date range rule ---

    print()
    print("=" * 60)
    print("CASE 5: event with end year before start year")
    print("=" * 60)

    sync_document(
        entity_indexer, fact_extractor, event_extractor,
        "Bitwa pod Arven", "Historia/Bitwa.md",
        {
            "tags": ["bitwa"],
            "data_od": "850",
            "data_do": "820",
        },
        "",
        now,
    )
    db.commit()

    result_5 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    range_conflict = db.query(Conflict).filter(
        Conflict.rule_name == "event_date_range"
    ).first()

    check(
        "swapped date_start/date_end detected",
        range_conflict is not None,
    )
    check(
        "range conflict references the battle entity",
        range_conflict is not None
        and range_conflict.entity.name == "Bitwa pod Arven",
    )

    # --- Relationship contradiction rule (plan section 6D) ---

    print()
    print("=" * 60)
    print("CASE 6: 'córka' vs 'siostra' of the same person (plan 6D)")
    print("=" * 60)

    father_doc = sync_document(
        entity_indexer, fact_extractor, event_extractor,
        "Aldren", "Postacie/Aldren.md",
        {"tags": ["Postać"]},
        "",
        now,
    )
    db.commit()

    elira_doc = sync_document(
        entity_indexer, fact_extractor, event_extractor,
        "Elira", "Postacie/Elira.md",
        {"tags": ["Postać"], "córka": "[[Aldren]]"},
        "Elira, [[Aldren]].",
        now,
    )
    db.commit()

    # Second source claims a contradictory relation for the same pair
    elira_entity = next(
        e for e in elira_doc.entities if e.name == "Elira"
    )
    aldren_entity = next(
        e for e in father_doc.entities if e.name == "Aldren"
    )

    from app.models import Fact as FactModel

    db.add(
        FactModel(
            subject_entity_id=elira_entity.id,
            predicate="siostra",
            object_entity_id=aldren_entity.id,
            document_id=elira_doc.id,
        )
    )
    db.commit()

    result_6 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    relationship_conflict = db.query(Conflict).filter(
        Conflict.rule_name == "relationship_contradiction"
    ).first()

    check(
        "'córka' vs 'siostra' of the same entity flagged",
        relationship_conflict is not None,
    )
    check(
        "relationship conflict references Elira",
        relationship_conflict is not None
        and relationship_conflict.entity.name == "Elira",
    )
    check(
        "relationship conflict has HIGH severity",
        relationship_conflict is not None
        and relationship_conflict.severity.value == "high",
    )

    # Sanity: compatible relationship terms must NOT conflict
    db.add(
        FactModel(
            subject_entity_id=elira_entity.id,
            predicate="dziecko",  # same group as "córka" -> compatible
            object_entity_id=aldren_entity.id,
            document_id=elira_doc.id,
        )
    )
    db.commit()

    conflicts_before = db.query(Conflict).filter(
        Conflict.rule_name == "relationship_contradiction"
    ).count()

    ConsistencyEngine(db, schema=schema).run()
    db.commit()

    conflicts_after = db.query(Conflict).filter(
        Conflict.rule_name == "relationship_contradiction"
    ).count()

    check(
        "synonymous relation terms ('córka'/'dziecko') do not conflict",
        conflicts_after == conflicts_before,
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
