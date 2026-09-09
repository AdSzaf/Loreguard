from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db_utils import ci_equals
from app.models import Conflict, ConflictSeverity, ConflictStatus, Document, Entity, Fact
from app.services.embedding_service import EmbeddingService
from app.services.llm_provider import LLMProvider
from app.services.retry_utils import call_with_rate_limit_retry


class SemanticConflictService:
    """
    Finds contradictions between documents that are worded
    completely differently but describe the same underlying claim
    (plan section 6/13 -- the plague-death-toll example: "zaraza w
    stolicy, 10 000 ofiar" vs "zaraza w Arven, 15 000 ofiar").

    Pipeline: embeddings narrow the whole vault down to documents
    that are plausibly ABOUT the same thing (cheap, no LLM), then
    only those candidate pairs get sent to the LLM to judge whether
    they actually conflict (expensive, used sparingly) -- exactly
    the architecture from plan section 14/27.

    Reuses the existing Fact/Conflict shape rather than adding new
    tables: each identified contradiction becomes two Facts
    (source_type="llm_semantic", one per document, holding the
    LLM's short claim + exact quote) and one Conflict linking them,
    so ConflictsView and everything else that already renders
    fact_a/fact_b needs zero changes to display these.

    Idempotent per initiating document: re-running replaces only
    the "llm_semantic" facts THIS document owns (cascades to their
    conflicts), same pattern as ProseFactExtractor.
    """

    name = "semantic_conflict"

    def __init__(
        self,
        db: Session,
        llm_provider: LLMProvider,
        embedding_service: EmbeddingService | None = None,
        similarity_threshold: float = 0.55,
        max_candidates: int = 5,
    ):
        self.db = db
        self.llm_provider = llm_provider
        self.embedding_service = embedding_service or EmbeddingService(db)
        self.similarity_threshold = similarity_threshold
        self.max_candidates = max_candidates

    def check_document(self, document: Document) -> dict:
        subject_entity = self.db.scalar(
            select(Entity).where(ci_equals(Entity.name, document.title))
        )

        if subject_entity is None:
            return {
                "checked_against": 0,
                "conflicts_found": 0,
                "error": (
                    "Document has no subject entity yet -- sync the "
                    "vault first."
                ),
            }

        if document.embedding is None:
            call_with_rate_limit_retry(
                self.embedding_service.update_document_embedding, document,
            )
            self.db.flush()

        similar = self.embedding_service.find_similar(
            document,
            limit=self.max_candidates,
            min_similarity=self.similarity_threshold,
        )

        # Idempotent: wipe this document's previously-found semantic
        # conflicts before re-checking. Facts on THIS document are
        # easy to find by document_id, but the paired fact lives on
        # the OTHER document -- found by following existing
        # Conflict rows first, since a plain document_id filter
        # would only clean up one side and leave the twin fact
        # orphaned (and the next Conflict count would drift).
        stale_conflicts = self.db.scalars(
            select(Conflict)
            .join(Fact, Conflict.fact_a_id == Fact.id)
            .where(
                Conflict.rule_name == self.name,
                Fact.document_id == document.id,
            )
        ).all()

        for stale_conflict in stale_conflicts:
            if stale_conflict.fact_b_id is not None:
                self.db.query(Fact).filter(
                    Fact.id == stale_conflict.fact_b_id
                ).delete(synchronize_session="fetch")

            self.db.delete(stale_conflict)

        self.db.flush()

        self.db.query(Fact).filter(
            Fact.document_id == document.id,
            Fact.source_type == "llm_semantic",
        ).delete(synchronize_session="fetch")

        conflicts_found = 0

        for other_doc, similarity in similar:
            candidates = call_with_rate_limit_retry(
                self.llm_provider.compare_texts,
                document.content or "",
                document.title,
                other_doc.content or "",
                other_doc.title,
            )

            for candidate in candidates:
                fact_a = Fact(
                    subject_entity_id=subject_entity.id,
                    predicate="semantic_claim",
                    object_value=candidate.claim_a,
                    document_id=document.id,
                    source_type="llm_semantic",
                    confidence=candidate.confidence,
                    source_text=candidate.quote_a or None,
                )
                fact_b = Fact(
                    subject_entity_id=subject_entity.id,
                    predicate="semantic_claim",
                    object_value=candidate.claim_b,
                    document_id=other_doc.id,
                    source_type="llm_semantic",
                    confidence=candidate.confidence,
                    source_text=candidate.quote_b or None,
                )
                self.db.add_all([fact_a, fact_b])
                self.db.flush()

                self.db.add(
                    Conflict(
                        entity_id=subject_entity.id,
                        rule_name=self.name,
                        severity=(
                            ConflictSeverity.HIGH
                            if candidate.confidence >= 0.85
                            else ConflictSeverity.MEDIUM
                        ),
                        confidence=max(0.0, min(1.0, candidate.confidence)),
                        status=ConflictStatus.OPEN,
                        explanation=(
                            f"Semantyczna sprzeczność między "
                            f"'{document.title}' a '{other_doc.title}' "
                            f"(podobieństwo tematyczne: "
                            f"{similarity:.0%}): "
                            f"'{candidate.claim_a}' vs "
                            f"'{candidate.claim_b}'"
                        ),
                        fact_a_id=fact_a.id,
                        fact_b_id=fact_b.id,
                    )
                )
                conflicts_found += 1

        document.semantic_check_hash = document.content_hash

        self.db.flush()

        return {
            "checked_against": len(similar),
            "conflicts_found": conflicts_found,
        }
