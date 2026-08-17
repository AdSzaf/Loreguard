from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Entity, EntityAlias, EntityType
from app.services.entity_extractor import EntityCandidate


class EntityResolver:
    """
    Resolves EntityCandidates against entities stored in the database.

    Resolution order:
        1. Exact entity name
        2. Existing alias
        3. Create a new Entity

    If a wikilink contains a different display name, it is stored
    as an alias of the resolved entity.
    """

    def __init__(self, db: Session):
        self.db = db

    def resolve(self, candidate: EntityCandidate) -> Entity:
        entity = self._find_by_name(candidate.name)

        if entity is None:
            entity = self._find_by_alias(candidate.name)

        if entity is None:
            entity = self._create_entity(candidate.name)

        if (
            candidate.display_name
            and candidate.display_name.casefold()
            != candidate.name.casefold()
        ):
            self._add_alias_if_missing(
                entity,
                candidate.display_name,
            )

        return entity

    def _find_by_name(self, name: str) -> Entity | None:
        return self.db.scalar(
            select(Entity).where(
                Entity.name.ilike(name)
            )
        )

    def _find_by_alias(self, alias: str) -> Entity | None:
        return self.db.scalar(
            select(Entity)
            .join(EntityAlias)
            .where(EntityAlias.alias.ilike(alias))
        )

    def _create_entity(self, name: str) -> Entity:
        entity = Entity(
            name=name,
            entity_type=EntityType.OTHER,
        )

        self.db.add(entity)
        self.db.flush()

        return entity

    def _add_alias_if_missing(
        self,
        entity: Entity,
        alias: str,
    ) -> None:
        existing_alias = next(
            (
                existing
                for existing in entity.aliases
                if existing.alias.casefold() == alias.casefold()
            ),
            None,
        )

        if existing_alias is not None:
            return

        entity.aliases.append(
            EntityAlias(alias=alias)
        )

        self.db.flush()