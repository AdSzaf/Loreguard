"""
Reproduces the exact real-world scenario the user hit while testing
manually, split into two clean, independent cases (a third case
chained onto the same entity would hit ExclusiveFactRule's existing
"only the first two distinct variants are compared" limitation --
see PROJECT_STATUS.md -- so this keeps each case to exactly two
facts per entity).

Run with:
    python test_predicate_synonyms.py
"""

import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.vault_schema import VaultSchema
from app.models import Conflict, Document, Entity, EntityType
from app.services.consistency_engine import ConsistencyEngine
from app.services.llm_provider import ExtractedFact, LLMProvider
from app.services.prose_fact_extractor import ProseFactExtractor


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


class FakeLLMProvider(LLMProvider):
    def __init__(self, scripted_responses):
        self._responses = list(scripted_responses)

    def extract_facts(self, text, known_entity_names):
        if not self._responses:
            return []
        return self._responses.pop(0)


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    schema = VaultSchema(Path("/tmp/loreguard_test_vault_does_not_exist"))
    now = datetime.datetime.utcnow()

    print("=" * 60)
    print("CASE 1: the user's exact scenario -- 'zginął' (linked to")
    print("           an event) vs 'umarł' (a literal year)")
    print("=" * 60)

    serigius = Entity(name="Serigius I", entity_type=EntityType.PERSON)
    battle = Entity(name="Bitwa pod Soizon", entity_type=EntityType.EVENT)
    db.add_all([serigius, battle])
    db.commit()

    battle_doc = Document(
        title="Bitwa pod Soizon",
        path="Wydarzenia/Bitwa_pod_Soizon.md",
        content="Zginął w niej Serigius I.",
        content_hash="battle-1",
        file_modified_at=now,
    )
    serigius_doc = Document(
        title="Serigius I",
        path="Postacie/Serigius_I.md",
        content="Umarł w 3030 K.E.",
        content_hash="serigius-1",
        file_modified_at=now,
    )
    db.add_all([battle_doc, serigius_doc])
    db.commit()

    fake_provider = FakeLLMProvider(
        scripted_responses=[
            [
                ExtractedFact(
                    subject="Serigius I",
                    predicate="zginął",
                    object="Bitwa pod Soizon",
                    confidence=0.9,
                    source_text="Zginął w niej Serigius I.",
                ),
            ],
            [
                ExtractedFact(
                    subject="Serigius I",
                    predicate="umarł",
                    object="3030 K.E.",
                    confidence=0.95,
                    source_text="Umarł w 3030 K.E.",
                ),
            ],
        ]
    )

    extractor = ProseFactExtractor(db, fake_provider)
    extractor.extract_from_document(battle_doc)
    db.commit()
    extractor.extract_from_document(serigius_doc)
    db.commit()

    result = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    # "zginął" and "umarł" now group under the same canonical
    # predicate ("died"). Their object values differ in *shape*
    # (an event reference vs a literal year) -- the rule can't know
    # whether the battle actually happened in 3030, so it correctly
    # surfaces this as "two different answers to how Serigius died",
    # which is a legitimate signal even without full precision.
    # (Confirming the battle's own year against 3030 is TODO #6,
    # "death_before_events", in PROJECT_STATUS.md.)
    check(
        "different-shaped death facts ARE surfaced as a conflict",
        result["created"] == 1,
    )

    conflict = db.query(Conflict).filter(
        Conflict.rule_name == "exclusive_fact"
    ).first()

    check(
        "explanation shows BOTH original words, not a fabricated one",
        "zginął" in conflict.explanation and "umarł" in conflict.explanation,
    )
    print(f"  explanation: {conflict.explanation}")

    print()
    print("=" * 60)
    print("CASE 2: pure synonym normalization -- two years, two words")
    print("=" * 60)

    other_person = Entity(name="Postać Testowa", entity_type=EntityType.PERSON)
    db.add(other_person)
    db.commit()

    doc_a = Document(
        title="Kronika A", path="Kronika_A.md",
        content="Postać Testowa umarła w roku 100.",
        content_hash="a-1", file_modified_at=now,
    )
    doc_b = Document(
        title="Kronika B", path="Kronika_B.md",
        content="Postać Testowa zmarła w roku 200.",
        content_hash="b-1", file_modified_at=now,
    )
    db.add_all([doc_a, doc_b])
    db.commit()

    provider_2 = FakeLLMProvider(
        scripted_responses=[
            [
                ExtractedFact(
                    subject="Postać Testowa", predicate="umarła",
                    object="100", confidence=0.9,
                    source_text="Postać Testowa umarła w roku 100.",
                ),
            ],
            [
                ExtractedFact(
                    subject="Postać Testowa", predicate="zmarła",
                    object="200", confidence=0.9,
                    source_text="Postać Testowa zmarła w roku 200.",
                ),
            ],
        ]
    )

    extractor_2 = ProseFactExtractor(db, provider_2)
    extractor_2.extract_from_document(doc_a)
    db.commit()
    extractor_2.extract_from_document(doc_b)
    db.commit()

    result_2 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check(
        "'umarła: 100' vs 'zmarła: 200' caught despite different words",
        result_2["created"] == 1,
    )

    conflict_2 = db.query(Conflict).filter(
        Conflict.rule_name == "exclusive_fact",
        Conflict.entity_id == other_person.id,
    ).first()

    check("conflict is about the right entity", conflict_2 is not None)
    check(
        "both original synonym words appear in the explanation",
        conflict_2 is not None
        and "umarła" in conflict_2.explanation
        and "zmarła" in conflict_2.explanation,
    )
    print(f"  explanation: {conflict_2.explanation}")

    print()
    print("=" * 60)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 60)

    db.close()

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
