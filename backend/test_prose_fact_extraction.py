"""
Self-contained test proving the ORIGINAL flagship scenario from the
project concept doc actually works end-to-end now:

    Bitwa_pod_Arven.md: "Aldren II zginął podczas oblężenia w 842."
    Historia_Valdoru.md: "Aldren II panował do 857, kiedy zginął."

Two documents, prose-only (no frontmatter dates), LLM-extracted
facts about the same person's death with two different years ->
ExclusiveFactRule should flag it as a conflict.

Uses a FakeLLMProvider (no real API key, no network) that returns
pre-scripted ExtractedFacts per document, so this is fully offline
and deterministic. It plugs into the exact same LLMProvider
interface AnthropicLLMProvider implements -- swapping one for the
other is the only thing that changes to go from "test" to "real".

Run with:
    python test_prose_fact_extraction.py
"""

import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.vault_schema import VaultSchema
from app.models import Conflict, Document, Entity, EntityType, Fact
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
    """Returns pre-scripted facts per call, keyed by call order."""

    def __init__(self, scripted_responses: list[list[ExtractedFact]]):
        self._responses = list(scripted_responses)
        self.calls: list[tuple[str, list[str]]] = []

    def extract_facts(
        self, text: str, known_entity_names: list[str]
    ) -> list[ExtractedFact]:
        self.calls.append((text, known_entity_names))

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

    # Aldren II already exists as a known entity (as it would after
    # EntityIndexer ran during a normal vault sync).
    aldren = Entity(name="Aldren II", entity_type=EntityType.PERSON)
    db.add(aldren)
    db.commit()

    battle_doc = Document(
        title="Bitwa pod Arven",
        path="Historia/Bitwa_pod_Arven.md",
        content=(
            "Bitwa pod Arven miała miejsce w 842 roku. Dowodził nią "
            "król Aldren II, który zginął podczas oblężenia."
        ),
        content_hash="battle-1",
        file_modified_at=now,
    )
    valdor_doc = Document(
        title="Historia Valdoru",
        path="Historia/Historia_Valdoru.md",
        content=(
            "Aldren II panował aż do 857 roku, kiedy został "
            "zamordowany przez własnego syna."
        ),
        content_hash="valdor-1",
        file_modified_at=now,
    )
    db.add_all([battle_doc, valdor_doc])
    db.commit()

    fake_provider = FakeLLMProvider(
        scripted_responses=[
            [
                ExtractedFact(
                    subject="Aldren II",
                    predicate="zmarł",
                    object="842",
                    confidence=0.95,
                    source_text="który zginął podczas oblężenia",
                ),
            ],
            [
                ExtractedFact(
                    subject="Aldren II",
                    predicate="zmarł",
                    object="857",
                    confidence=0.9,
                    source_text="kiedy został zamordowany przez własnego syna",
                ),
            ],
        ]
    )

    prose_extractor = ProseFactExtractor(db, fake_provider)

    print("=" * 60)
    print("CASE 1: LLM extraction produces grounded Facts")
    print("=" * 60)

    battle_facts = prose_extractor.extract_from_document(battle_doc)
    db.commit()

    check("one fact extracted from the battle article", len(battle_facts) == 1)
    check(
        "fact is attached to the EXISTING Aldren II entity, not a new one",
        battle_facts[0].subject_entity_id == aldren.id,
    )
    check(
        "source_type is 'llm_prose'",
        battle_facts[0].source_type == "llm_prose",
    )
    check(
        "confidence carried through from the LLM response",
        battle_facts[0].confidence == 0.95,
    )
    check(
        "source_text (the quote) is preserved",
        "zginął podczas oblężenia" in (battle_facts[0].source_text or ""),
    )

    valdor_facts = prose_extractor.extract_from_document(valdor_doc)
    db.commit()

    check("one fact extracted from the second article", len(valdor_facts) == 1)

    print()
    print("=" * 60)
    print("CASE 2: the flagship conflict is actually detected")
    print("=" * 60)

    result = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    check("exactly one conflict created", result["created"] == 1)

    conflict = db.query(Conflict).filter(
        Conflict.rule_name == "exclusive_fact"
    ).first()

    check("conflict exists", conflict is not None)
    check(
        "conflict is about Aldren II",
        conflict is not None and conflict.entity.name == "Aldren II",
    )
    check(
        "explanation mentions both conflicting years",
        conflict is not None
        and "842" in conflict.explanation
        and "857" in conflict.explanation,
    )

    print(f"  explanation: {conflict.explanation}")

    print()
    print("=" * 60)
    print("CASE 3: subjects not matching a known entity are dropped")
    print("=" * 60)

    unknown_doc = Document(
        title="Fragment nieznany",
        path="Fragment.md",
        content="Ktoś nieznany zrobił coś kiedyś.",
        content_hash="unknown-1",
        file_modified_at=now,
    )
    db.add(unknown_doc)
    db.commit()

    ungrounded_provider = FakeLLMProvider(
        scripted_responses=[
            [
                ExtractedFact(
                    subject="Postać Wymyślona Przez LLM",
                    predicate="zrobił",
                    object="coś",
                    confidence=0.6,
                    source_text="Ktoś nieznany zrobił coś kiedyś.",
                ),
            ],
        ]
    )

    ungrounded_extractor = ProseFactExtractor(db, ungrounded_provider)
    ungrounded_facts = ungrounded_extractor.extract_from_document(unknown_doc)
    db.commit()

    check(
        "fact about a non-existent entity is silently dropped, not invented",
        len(ungrounded_facts) == 0,
    )

    print()
    print("=" * 60)
    print("CASE 4: re-extraction is idempotent and doesn't touch")
    print("           frontmatter facts owned by FactExtractor")
    print("=" * 60)

    # Simulate a frontmatter fact already existing on the battle doc
    frontmatter_fact = Fact(
        subject_entity_id=aldren.id,
        predicate="tytul",
        object_value="Król",
        document_id=battle_doc.id,
        source_type="frontmatter",
        confidence=1.0,
    )
    db.add(frontmatter_fact)
    db.commit()

    # Re-running extraction on unchanged text should yield the same
    # fact again (the LLM would say the same thing) -- give the fake
    # provider one more scripted response to simulate that.
    fake_provider._responses.append(
        [
            ExtractedFact(
                subject="Aldren II",
                predicate="zmarł",
                object="842",
                confidence=0.95,
                source_text="który zginął podczas oblężenia",
            ),
        ]
    )

    prose_extractor.extract_from_document(battle_doc)
    db.commit()

    remaining = db.query(Fact).filter(
        Fact.document_id == battle_doc.id
    ).all()

    check(
        "frontmatter fact survives an LLM re-extraction on the same doc",
        any(f.source_type == "frontmatter" for f in remaining),
    )
    check(
        "no duplicate llm_prose facts after re-extraction",
        sum(1 for f in remaining if f.source_type == "llm_prose") == 1,
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
