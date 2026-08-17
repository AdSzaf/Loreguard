from sqlalchemy import ForeignKey, String
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

    subject: Mapped["Entity"] = relationship(
        foreign_keys=[subject_entity_id],
    )

    object_entity: Mapped["Entity | None"] = relationship(
        foreign_keys=[object_entity_id],
    )

    document: Mapped["Document"] = relationship()