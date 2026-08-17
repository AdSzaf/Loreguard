from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EntityAlias(Base):
    __tablename__ = "entity_aliases"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    alias: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship(
        back_populates="aliases",
    )