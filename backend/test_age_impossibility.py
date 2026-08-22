"""
Reproduces the exact Elira example from the project's original
concept document (plan section 26):

    Elira.md: "Elira urodziła się w 824 roku."
    Wojna.md: "W 842 roku Elira, mająca zaledwie 12 lat, objęła
               dowództwo nad armią Valdoru."

Expected age in 842 (born 824) = 18, but the text claims 12 ->
should be flagged. Also tests the negative case: matching ages
must NOT be flagged.

Run with:
    python test_age_impossibility.py
"""

import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.vault_schema import VaultSchema
from app.models import Conflict, Document, Entity, EntityType, Event
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
    print("CASE 1: the plan's own Elira example -- age doesn't match")
    print("=" * 60)

    elira = Entity(name="Elira", entity_type=EntityType.PERSON)
    war_entity = Entity(name="Wojna", entity_type=EntityType.EVENT)
    db.add_all([elira, war_entity])
    db.commit()

    elira_doc = Document(
        title="Elira", path="Postacie/Elira.md",
        content="Elira urodziła się w 824 roku.",
        content_hash="elira-1", file_modified_at=now,
    )
    war_doc = Document(
        title="Wojna", path="Wydarzenia/Wojna.md",
        content=(
            "W 842 roku Elira, mająca zaledwie 12 lat, objęła "
            "dowództwo nad armią Valdoru."
        ),
        content_hash="wojna-1", file_modified_at=now,
    )
    db.add_all([elira_doc, war_doc])
    db.commit()

    # Mirrors what EventExtractor produces from frontmatter
    # (data_wydarzenia: 842) -- AgeImpossibilityRule reads this,
    # not raw LLM output.
    db.add(Event(
        entity_id=war_entity.id, document_id=war_doc.id,
        date_text="842", date_start_year=842, date_end_year=842,
    ))
    db.commit()

    provider = FakeLLMProvider(
        scripted_responses=[
            [
                ExtractedFact(
                    subject="Elira", predicate="urodziła się",
                    object="824", confidence=0.95,
                    source_text="Elira urodziła się w 824 roku.",
                ),
            ],
            [
                ExtractedFact(
                    subject="Elira", predicate="wiek_podczas",
                    object="Wojna", object_number=12, confidence=0.9,
                    source_text="mająca zaledwie 12 lat",
                ),
            ],
        ]
    )

    extractor = ProseFactExtractor(db, provider)
    extractor.extract_from_document(elira_doc)
    db.commit()
    extractor.extract_from_document(war_doc)
    db.commit()

    result = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check(
        "age impossibility detected (expected 18, stated 12)",
        result["created"] == 1,
    )

    conflict = db.query(Conflict).filter(
        Conflict.rule_name == "age_impossibility"
    ).first()

    check("conflict exists and is about Elira", conflict is not None and conflict.entity.name == "Elira")
    check("explanation shows expected age (18)", "18" in conflict.explanation)
    check("explanation shows stated age (12)", "12" in conflict.explanation)
    check("explanation shows the event year (842)", "842" in conflict.explanation)
    check("explanation shows birth year (824)", "824" in conflict.explanation)
    print(f"  explanation: {conflict.explanation}")

    print()
    print("=" * 60)
    print("CASE 2: matching age must NOT be flagged (no false positive)")
    print("=" * 60)

    correct_person = Entity(name="Osoba Poprawna", entity_type=EntityType.PERSON)
    correct_event_entity = Entity(name="Wydarzenie Poprawne", entity_type=EntityType.EVENT)
    db.add_all([correct_person, correct_event_entity])
    db.commit()

    correct_person_doc = Document(
        title="Osoba Poprawna", path="Osoba_Poprawna.md",
        content="Osoba Poprawna urodziła się w roku 100.",
        content_hash="correct-person-1", file_modified_at=now,
    )
    correct_event_doc = Document(
        title="Wydarzenie Poprawne", path="Wydarzenie_Poprawne.md",
        content="W roku 120, mając 20 lat, Osoba Poprawna wzięła udział.",
        content_hash="correct-event-1", file_modified_at=now,
    )
    db.add_all([correct_person_doc, correct_event_doc])
    db.commit()

    db.add(Event(
        entity_id=correct_event_entity.id, document_id=correct_event_doc.id,
        date_text="120", date_start_year=120, date_end_year=120,
    ))
    db.commit()

    provider_2 = FakeLLMProvider(
        scripted_responses=[
            [
                ExtractedFact(
                    subject="Osoba Poprawna", predicate="urodziła się",
                    object="100", confidence=0.95,
                    source_text="Osoba Poprawna urodziła się w roku 100.",
                ),
            ],
            [
                ExtractedFact(
                    subject="Osoba Poprawna", predicate="wiek_podczas",
                    object="Wydarzenie Poprawne", object_number=20,
                    confidence=0.9,
                    source_text="mając 20 lat",
                ),
            ],
        ]
    )

    extractor_2 = ProseFactExtractor(db, provider_2)
    extractor_2.extract_from_document(correct_person_doc)
    db.commit()
    extractor_2.extract_from_document(correct_event_doc)
    db.commit()

    result_2 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check(
        "120 - 100 = 20, matches stated age -> NO false-positive conflict",
        result_2["created"] == 0,
    )

    print()
    print("=" * 60)
    print("CASE 3: missing birth year -> no guess, no conflict")
    print("=" * 60)

    mystery_person = Entity(name="Osoba Bez Daty", entity_type=EntityType.PERSON)
    mystery_event_entity = Entity(name="Wydarzenie Bez Kontekstu", entity_type=EntityType.EVENT)
    db.add_all([mystery_person, mystery_event_entity])
    db.commit()

    mystery_doc = Document(
        title="Wydarzenie Bez Kontekstu", path="Wydarzenie_Bez_Kontekstu.md",
        content="Mając 30 lat, Osoba Bez Daty coś zrobiła.",
        content_hash="mystery-1", file_modified_at=now,
    )
    db.add(mystery_doc)
    db.commit()

    db.add(Event(
        entity_id=mystery_event_entity.id, document_id=mystery_doc.id,
        date_text="500", date_start_year=500, date_end_year=500,
    ))
    db.commit()

    provider_3 = FakeLLMProvider(
        scripted_responses=[
            [
                ExtractedFact(
                    subject="Osoba Bez Daty", predicate="wiek_podczas",
                    object="Wydarzenie Bez Kontekstu", object_number=30,
                    confidence=0.9,
                    source_text="Mając 30 lat",
                ),
            ],
        ]
    )

    extractor_3 = ProseFactExtractor(db, provider_3)
    extractor_3.extract_from_document(mystery_doc)
    db.commit()

    result_3 = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check(
        "no birth year on record -> rule stays silent, doesn't guess",
        db.query(Conflict).filter(
            Conflict.rule_name == "age_impossibility",
            Conflict.entity_id == mystery_person.id,
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
