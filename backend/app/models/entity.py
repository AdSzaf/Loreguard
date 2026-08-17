from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EntityType(str, PyEnum):
    PERSON = "person"
    PLACE = "place"
    COUNTRY = "country"
    REGION = "region"
    RACE = "race"
    ORGANIZATION = "organization"
    FACTION = "faction"
    DEITY = "deity"
    ITEM = "item"
    EVENT = "event"
    CONCEPT = "concept"
    OTHER = "other"


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    aliases: Mapped[list["EntityAlias"]] = relationship(
        back_populates="entity",
        cascade="all, delete-orphan",
    )

    documents: Mapped[list["Document"]] = relationship(
        secondary="document_entities",
        back_populates="entities",
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