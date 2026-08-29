from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.embedding_vector import EmbeddingVector


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        unique=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    entities: Mapped[list["Entity"]] = relationship(
        secondary="document_entities",
        back_populates="documents",
    )

    file_modified_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        EmbeddingVector,
        nullable=True,
    )

    embedding_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # content_hash the LLM prose extractor last successfully ran
    # against. Compared to `content_hash` to decide, incrementally,
    # which documents actually need (re-)processing -- None means
    # "never processed". Set by ProseFactExtractor itself, not by
    # the caller, so this invariant can't be forgotten at a call site.
    llm_facts_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # Same idea as llm_facts_hash, but for semantic (cross-document)
    # conflict checking -- set by SemanticConflictService itself.
    # Note: only tracks whether THIS document's own content changed
    # since its last check, not whether a newly-added similar
    # document elsewhere might now be worth comparing against; a
    # force re-check covers that case.
    semantic_check_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )