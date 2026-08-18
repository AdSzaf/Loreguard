from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.vault_schema import VaultSchema
from app.models import Document, Entity, EntityAlias, EntityType
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

    def __init__(self, db: Session, schema: VaultSchema):
        self.db = db
        self.schema = schema

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

    def resolve_subject(
        self,
        document: Document,
        frontmatter: dict,
    ) -> Entity:
        """
        Finds or creates the Entity that a document is *about*
        (its own canonical entity, keyed by document title) and
        keeps its entity_type in sync with the document's `tags`.

        Unlike `resolve()`, this never leaves an entity uncreated:
        every document gets a subject entity on first sync, even if
        nothing else in the vault links to it yet. Without this,
        facts/events extracted from an unlinked note's frontmatter
        would have nowhere to attach.
        """

        entity = self._find_by_name(document.title)

        if entity is None:
            entity = self._find_by_alias(document.title)

        resolved_type = self.schema.resolve_entity_type(
            frontmatter.get("tags")
        )

        if entity is None:
            entity = Entity(
                name=document.title,
                entity_type=resolved_type or EntityType.OTHER,
            )
            self.db.add(entity)
            self.db.flush()
        elif resolved_type is not None and entity.entity_type != resolved_type:
            entity.entity_type = resolved_type

        return entity

    def _escape_like(self, val: str) -> str:
        """Eskapuje znaki specjalne dla klauzuli LIKE/ILIKE."""
        return val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _find_by_name(self, name: str) -> Entity | None:
        return self.db.scalar(
            select(Entity).where(
                Entity.name.ilike(self._escape_like(name))
            )
        )

    def _find_by_alias(self, alias: str) -> Entity | None:
        return self.db.scalar(
            select(Entity)
            .join(EntityAlias)
            .where(EntityAlias.alias.ilike(self._escape_like(alias)))
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