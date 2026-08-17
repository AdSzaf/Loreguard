from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DatePrecision(str, PyEnum):
    """
    How precisely a date is known.

    Fantasy sources rarely give exact dates. We keep the raw text
    the author wrote (date_text) for display/provenance, plus a
    normalized year range for comparisons and conflict detection.
    """

    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class Event(Base):
    """
    Structured data for an Entity of type EVENT.

    An event is still an Entity first (so it gets a name, aliases,
    and document links "for free"). This table adds the fields a
    plain Entity does not have: when it happened, where, and what
    the outcome was. Participants live in EventParticipant, since
    an event can have many participants with different roles.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    date_text: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    date_start_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    date_end_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    precision: Mapped[DatePrecision] = mapped_column(
        Enum(DatePrecision),
        nullable=False,
        default=DatePrecision.UNKNOWN,
    )

    location_entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )

    outcome: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship(
        foreign_keys=[entity_id],
    )

    location: Mapped["Entity | None"] = relationship(
        foreign_keys=[location_entity_id],
    )

    document: Mapped["Document"] = relationship()

    participants: Mapped[list["EventParticipant"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
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
