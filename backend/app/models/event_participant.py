from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EventParticipant(Base):
    """
    Links an Entity (usually a Person, Faction, or Country) to an
    Event, optionally tagged with the role it played.

    Example roles: "commander", "participant", "victim", "witness".
    role is intentionally a free-text field for now, matching the
    pragmatic, frontmatter-driven style of FactExtractor. It can be
    tightened into an enum later if patterns emerge.
    """

    __tablename__ = "event_participants"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )

    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    event: Mapped["Event"] = relationship(
        back_populates="participants",
    )

    entity: Mapped["Entity"] = relationship()
