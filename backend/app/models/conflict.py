from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ConflictStatus(str, PyEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    EXPLAINED = "explained"


class ConflictSeverity(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Conflict(Base):
    """
    A potential inconsistency found by the rule engine (and later,
    by semantic LLM comparison). LoreGuard never edits the vault --
    it only surfaces conflicts; `status` records what the person
    decided (see project concept: "strażnik kanonu", not an editor).

    Evidence is one of two shapes, depending on rule_name:
      - fact_a_id + fact_b_id: two Facts disagree about a subject
      - related_event_id: a single Event is internally inconsistent

    Exactly one shape is populated for a given conflict.
    """

    __tablename__ = "conflicts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    rule_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    severity: Mapped[ConflictSeverity] = mapped_column(
        Enum(ConflictSeverity),
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    status: Mapped[ConflictStatus] = mapped_column(
        Enum(ConflictStatus),
        nullable=False,
        default=ConflictStatus.OPEN,
    )

    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    fact_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("facts.id", ondelete="CASCADE"),
        nullable=True,
    )

    fact_b_id: Mapped[int | None] = mapped_column(
        ForeignKey("facts.id", ondelete="CASCADE"),
        nullable=True,
    )

    related_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=True,
    )

    resolution_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    entity: Mapped["Entity"] = relationship()

    fact_a: Mapped["Fact | None"] = relationship(
        foreign_keys=[fact_a_id],
    )

    fact_b: Mapped["Fact | None"] = relationship(
        foreign_keys=[fact_b_id],
    )

    related_event: Mapped["Event | None"] = relationship()

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
