"""
Reproduces every false positive the user found running the real
app against their live vault, to lock in the fix permanently.

Run with:
    python test_exclusivity_allowlist.py
"""

import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.vault_schema import VaultSchema
from app.models import Conflict, Entity, EntityType, Fact
from app.services.consistency_engine import ConsistencyEngine


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

    schema = VaultSchema(Path("/tmp/loreguard_test_vault_does_not_exist"))

    print("=" * 60)
    print("Real false positives from the user's live vault -- must")
    print("           ALL now produce zero conflicts")
    print("=" * 60)

    # Each of these mirrors a real case reported: a deity or place
    # with two "descriptive" facts under a generic predicate that
    # are complementary, not contradictory.
    cases = [
        ("Magnia", EntityType.COUNTRY, "ogłasza", "Era Bogów", "Era Rozkwitu"),
        ("Zulios", EntityType.DEITY, "być", "Strażnik Czasu", "pierwotne bóstwo czasu"),
        ("Omir", EntityType.DEITY, "był", "wieczny sędzia", "bóg sprawiedliwości"),
        ("Naumir", EntityType.DEITY, "jest bogiem", "astronomia", "żeglugi"),
        ("Nadea", EntityType.DEITY, "wyzwana_na_pojedynek", "Rosenia", "Kogust"),
        ("Woh", EntityType.DEITY, "być", "bóstwo Pierwotne", "Wohtor"),
        ("Rosenia", EntityType.DEITY, "jest boginią", "Lasów", "zbieractwa"),
        ("Solumin", EntityType.DEITY, "jest", "bóg słońca", "bóg przyjazny wszystkim stworzeniom"),
        ("Tarus", EntityType.DEITY, "był czczony przez", "Giganci", "potwory zrodzone z ziemi"),
    ]

    for name, entity_type, predicate, value_a, value_b in cases:
        entity = Entity(name=name, entity_type=entity_type)
        db.add(entity)
        db.flush()

        from app.models import Document

        doc = Document(
            title=name, path=f"{name}.md", content="",
            content_hash=name, file_modified_at=datetime.datetime.utcnow(),
        )
        db.add(doc)
        db.flush()

        db.add(Fact(
            subject_entity_id=entity.id, predicate=predicate,
            object_value=value_a, document_id=doc.id,
        ))
        db.add(Fact(
            subject_entity_id=entity.id, predicate=predicate,
            object_value=value_b, document_id=doc.id,
        ))
        db.commit()

    result = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check(
        f"all {len(cases)} real-world false positives now produce ZERO conflicts",
        result["created"] == 0,
    )
    check(
        "no Conflict rows exist for any of these entities",
        db.query(Conflict).count() == 0,
    )

    print()
    print("=" * 60)
    print("The one TRUE positive (Serigius) must still be caught")
    print("=" * 60)

    serigius = Entity(name="Serigius I", entity_type=EntityType.PERSON)
    db.add(serigius)
    db.flush()

    from app.models import Document

    doc = Document(
        title="Serigius I", path="Serigius.md", content="",
        content_hash="serigius", file_modified_at=datetime.datetime.utcnow(),
    )
    db.add(doc)
    db.flush()

    db.add(Fact(
        subject_entity_id=serigius.id, predicate="umarł",
        object_value="3030", document_id=doc.id,
    ))
    db.add(Fact(
        subject_entity_id=serigius.id, predicate="zginął",
        object_value="2996", document_id=doc.id,
    ))
    db.commit()

    result_2 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check(
        "conflicting death years for a PERSON still correctly flagged",
        result_2["created"] == 1,
    )

    print()
    print("=" * 60)
    print("DEITY reincarnation exemption: multiple born/died is fine")
    print("=" * 60)

    reincarnating_deity = Entity(
        name="Bóstwo Wieczne", entity_type=EntityType.DEITY
    )
    db.add(reincarnating_deity)
    db.flush()

    deity_doc = Document(
        title="Bóstwo Wieczne", path="Bostwo_Wieczne.md", content="",
        content_hash="deity", file_modified_at=datetime.datetime.utcnow(),
    )
    db.add(deity_doc)
    db.flush()

    db.add(Fact(
        subject_entity_id=reincarnating_deity.id, predicate="umarł",
        object_value="100", document_id=deity_doc.id,
    ))
    db.add(Fact(
        subject_entity_id=reincarnating_deity.id, predicate="zginął",
        object_value="500", document_id=deity_doc.id,
    ))
    db.commit()

    result_3 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check(
        "a DEITY with two different death years (reincarnation) is NOT flagged",
        db.query(Conflict).filter(
            Conflict.entity_id == reincarnating_deity.id
        ).count() == 0,
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
