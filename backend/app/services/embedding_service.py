import datetime
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document
from app.services.embedding_provider import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
)


class EmbeddingService:
    """
    Computes and stores a per-document embedding, and finds similar
    documents by cosine similarity.

    This is the "before the LLM" half of plan section 13/27: rather
    than handing an LLM the whole vault when checking a new/edited
    document for conflicts, find_similar() narrows that down to a
    handful of related documents first. Step 19 (LLM) is expected
    to call this before doing any semantic comparison.

    Similarity is computed in Python over all embedded documents --
    fine up to at least a few thousand documents. See
    EmbeddingVector's docstring for the upgrade path to SQL-side
    search via pgvector if a vault ever outgrows that.
    """

    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider | None = None,
    ):
        self.db = db
        self.provider = provider or HashingEmbeddingProvider()

    def update_document_embedding(self, document: Document) -> None:
        text = f"{document.title}\n\n{document.content or ''}".strip()

        if not text:
            document.embedding = None
            document.embedding_updated_at = None
            return

        document.embedding = self.provider.embed(text)
        document.embedding_updated_at = datetime.datetime.utcnow()

    def reembed_all(self) -> int:
        """
        Recomputes embeddings for every document. Needed after
        switching EmbeddingProvider (different providers/dimensions
        produce vectors that aren't comparable to each other).
        """

        documents = self.db.scalars(select(Document)).all()

        for document in documents:
            self.update_document_embedding(document)

        self.db.flush()

        return len(documents)

    def find_similar(
        self,
        document: Document,
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> list[tuple[Document, float]]:
        if document.embedding is None:
            return []

        candidates = self.db.scalars(
            select(Document).where(
                Document.id != document.id,
                Document.embedding.is_not(None),
            )
        ).all()

        scored = [
            (candidate, self._cosine_similarity(document.embedding, candidate.embedding))
            for candidate in candidates
        ]

        scored = [
            pair for pair in scored if pair[1] >= min_similarity
        ]

        scored.sort(key=lambda pair: pair[1], reverse=True)

        return scored[:limit]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)
