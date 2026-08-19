from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    subject_entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    predicate: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    object_entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=True,
    )

    object_value: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # "frontmatter" (deterministic, parsed from YAML) or "llm_prose"
    # (extracted from body text by an LLMProvider). Facts are
    # replaced-on-resync per source_type independently, so an LLM
    # re-extraction never wipes out frontmatter facts and vice versa.
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="frontmatter",
        server_default="frontmatter",
    )

    # How confident the source is that this fact is correct.
    # Frontmatter facts are authored directly, so they default to
    # 1.0. LLM-extracted facts get a real confidence score from the
    # model and are never silently treated as ground truth.
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        server_default="1.0",
    )

    # The exact sentence/span the fact was extracted from, so a
    # conflict card can show "according to X.md: '...'" (plan
    # section 10/20) instead of just the structured predicate.
    source_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    subject: Mapped["Entity"] = relationship(
        foreign_keys=[subject_entity_id],
    )

    object_entity: Mapped["Entity | None"] = relationship(
        foreign_keys=[object_entity_id],
    )

    document: Mapped["Document"] = relationship()