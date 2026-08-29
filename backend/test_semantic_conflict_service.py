"""
Reproduces the exact "plague death toll" example from the project's
original concept doc (plan section 13/6): two articles describing
the same event in completely different words, with conflicting
numbers. Uses fake embedding + LLM providers -- no real API calls.

Run with:
    python test_semantic_conflict_service.py
"""

import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import Conflict, Document, Entity, EntityType, Fact
from app.services.embedding_provider import EmbeddingProvider
from app.services.embedding_service import EmbeddingService
from app.services.llm_provider import (
    LLMProvider,
    SemanticConflictCandidate,
)
from app.services.semantic_conflict_service import SemanticConflictService


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


class FakeEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic fake: two "similar topic" docs get near-identical
    vectors, an unrelated doc gets an orthogonal one. Simulates what
    a real semantic embedding model would produce for topically
    related text, without any network call.
    """

    dimensions = 4

    def embed(self, text: str) -> list[float]:
        if "zaraza" in text.lower() or "epidemi" in text.lower():
            # Near-identical, small deterministic variation
            variation = 0.01 if "arven" in text.lower() else 0.0
            return [0.9 + variation, 0.1, 0.1, 0.1]

        return [0.1, 0.9, 0.1, 0.1]


class FakeLLMProvider(LLMProvider):
    def __init__(self, scripted_responses):
        self._responses = list(scripted_responses)
        self.calls = []

    def extract_facts(self, text, known_entity_names):
        return []

    def compare_texts(self, text_a, title_a, text_b, title_b):
        self.calls.append((title_a, title_b))

        if not self._responses:
            return []

        return self._responses.pop(0)


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    now = datetime.datetime.utcnow()

    print("=" * 60)
    print("CASE 1: the plan's own plague example -- different words,")
    print("           conflicting death toll, must be caught")
    print("=" * 60)

    magnia = Entity(name="Wielka Zaraza", entity_type=EntityType.EVENT)
    db.add(magnia)
    db.commit()

    doc_a = Document(
        title="Wielka Zaraza",
        path="Wielka_Zaraza.md",
        content=(
            "Podczas wielkiej zarazy w stolicy zginęło ponad "
            "dziesięć tysięcy mieszkańców."
        ),
        content_hash="plague-a",
        file_modified_at=now,
    )
    doc_b = Document(
        title="Kroniki Arven",
        path="Kroniki_Arven.md",
        content=(
            "Zaraza, która nawiedziła Arven, pochłonęła około "
            "piętnastu tysięcy istnień."
        ),
        content_hash="plague-b",
        file_modified_at=now,
    )
    doc_unrelated = Document(
        title="Historia Magii",
        path="Historia_Magii.md",
        content="Magia dzieli się na kilka szkół, każda ze swoimi zasadami.",
        content_hash="unrelated-1",
        file_modified_at=now,
    )
    db.add_all([doc_a, doc_b, doc_unrelated])
    db.commit()

    embedding_service = EmbeddingService(db, FakeEmbeddingProvider())
    for doc in (doc_a, doc_b, doc_unrelated):
        embedding_service.update_document_embedding(doc)
    db.commit()

    llm_provider = FakeLLMProvider(
        scripted_responses=[
            [
                SemanticConflictCandidate(
                    claim_a="liczba ofiar: ponad 10000",
                    claim_b="liczba ofiar: około 15000",
                    quote_a="zginęło ponad dziesięć tysięcy mieszkańców",
                    quote_b="pochłonęła około piętnastu tysięcy istnień",
                    confidence=0.9,
                ),
            ],
        ]
    )

    service = SemanticConflictService(
        db, llm_provider, embedding_service, similarity_threshold=0.5,
    )
    result = service.check_document(doc_a)
    db.commit()

    check("checked against exactly 1 similar document", result["checked_against"] == 1)
    check(
        "unrelated document (different topic) was NOT compared",
        all(call[1] != "Historia Magii" for call in llm_provider.calls),
    )
    check("one semantic conflict found", result["conflicts_found"] == 1)

    conflict = db.query(Conflict).filter(
        Conflict.rule_name == "semantic_conflict"
    ).first()

    check("conflict was created", conflict is not None)
    check(
        "explanation names both documents",
        conflict is not None
        and "Wielka Zaraza" in conflict.explanation
        and "Kroniki Arven" in conflict.explanation,
    )
    print(f"  explanation: {conflict.explanation}")

    check(
        "two llm_semantic Facts created (one per document)",
        db.query(Fact).filter(Fact.source_type == "llm_semantic").count() == 2,
    )
    check(
        "source_text (exact quotes) preserved",
        conflict.fact_a.source_text is not None
        and conflict.fact_b.source_text is not None,
    )

    print()
    print("=" * 60)
    print("CASE 2: re-checking is idempotent (no duplicate conflicts)")
    print("=" * 60)

    llm_provider._responses.append(
        [
            SemanticConflictCandidate(
                claim_a="liczba ofiar: ponad 10000",
                claim_b="liczba ofiar: około 15000",
                quote_a="zginęło ponad dziesięć tysięcy mieszkańców",
                quote_b="pochłonęła około piętnastu tysięcy istnień",
                confidence=0.9,
            ),
        ]
    )

    service.check_document(doc_a)
    db.commit()

    check(
        "still exactly one semantic conflict after re-check",
        db.query(Conflict).filter(
            Conflict.rule_name == "semantic_conflict"
        ).count() == 1,
    )
    check(
        "still exactly 2 llm_semantic facts (old ones replaced, not accumulated)",
        db.query(Fact).filter(Fact.source_type == "llm_semantic").count() == 2,
    )

    print()
    print("=" * 60)
    print("CASE 3: no similar documents -> no LLM calls, no conflicts")
    print("=" * 60)

    llm_provider_2 = FakeLLMProvider(scripted_responses=[])
    result_3 = SemanticConflictService(
        db, llm_provider_2, embedding_service, similarity_threshold=0.5,
    ).check_document(doc_unrelated)
    db.commit()

    check("no candidates found for the unrelated document", result_3["checked_against"] == 0)
    check("no LLM calls made", len(llm_provider_2.calls) == 0)

    print()
    print("=" * 60)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 60)

    db.close()

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
