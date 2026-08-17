import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, Entity, EntityAlias, Fact
from app.schemas.document import ParsedDocument
from app.services.entity_extractor import EntityExtractor


class FactExtractor:
    """
    Extracts structured facts from Obsidian frontmatter.
    """

    IGNORED_FIELDS = {
        "aliases",
        "tags",
    }

    WIKILINK_PATTERN = re.compile(
        r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]"
    )

    def __init__(self, db: Session):
        self.db = db
        self.entity_extractor = EntityExtractor()

    def extract_from_document(
        self,
        document: Document,
        parsed_document: ParsedDocument,
    ) -> list[Fact]:
        subject = self._find_subject_entity(document)

        if subject is None:
            return []

        facts: list[Fact] = []

        for predicate, raw_value in parsed_document.frontmatter.items():
            if predicate in self.IGNORED_FIELDS:
                continue

            if raw_value is None:
                continue

            value = self._serialize_value(raw_value)

            if not value:
                continue

            linked_entity = self._resolve_wikilink_entity(value)

            if linked_entity is not None:
                fact = Fact(
                    subject_entity_id=subject.id,
                    predicate=predicate,
                    object_entity_id=linked_entity.id,
                    object_value=None,
                    document_id=document.id,
                )
            else:
                fact = Fact(
                    subject_entity_id=subject.id,
                    predicate=predicate,
                    object_entity_id=None,
                    object_value=value,
                    document_id=document.id,
                )

            self.db.add(fact)
            facts.append(fact)

        self.db.flush()

        return facts

    def _find_subject_entity(
        self,
        document: Document,
    ) -> Entity | None:

        entity = self.db.scalar(
            select(Entity).where(
                Entity.name.ilike(document.title)
            )
        )

        if entity is not None:
            return entity

        return self.db.scalar(
            select(Entity)
            .join(EntityAlias)
            .where(
                EntityAlias.alias.ilike(document.title)
            )
        )

    def _resolve_wikilink_entity(
        self,
        value: str,
    ) -> Entity | None:

        match = self.WIKILINK_PATTERN.fullmatch(
            value.strip()
        )

        if not match:
            return None

        entity_name = match.group(1).strip()

        return self.db.scalar(
            select(Entity).where(
                Entity.name.ilike(entity_name)
            )
        )

    @staticmethod
    def _serialize_value(value) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)

        if isinstance(value, dict):
            return ", ".join(
                f"{key}: {val}"
                for key, val in value.items()
            )

        return str(value).strip()