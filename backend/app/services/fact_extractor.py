from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db_utils import ci_equals
from app.core.wikilinks import parse_wikilink
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

        # Re-syncing the same document (e.g. after an edit, or on
        # every vault watcher tick) must not accumulate duplicate
        # or stale facts. Only frontmatter-sourced facts for this
        # document are replaced -- LLM-extracted facts (source_type
        # "llm_prose") are owned by ProseFactExtractor and must
        # survive a plain frontmatter re-sync untouched.
        self.db.query(Fact).filter(
            Fact.document_id == document.id,
            Fact.source_type == "frontmatter",
        ).delete(synchronize_session=False)

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
                    source_type="frontmatter",
                    confidence=1.0,
                )
            else:
                fact = Fact(
                    subject_entity_id=subject.id,
                    predicate=predicate,
                    object_entity_id=None,
                    object_value=value,
                    document_id=document.id,
                    source_type="frontmatter",
                    confidence=1.0,
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
                ci_equals(Entity.name, document.title)
            )
        )

        if entity is not None:
            return entity

        return self.db.scalar(
            select(Entity)
            .join(EntityAlias)
            .where(
                ci_equals(EntityAlias.alias, document.title)
            )
        )

    def _resolve_wikilink_entity(
        self,
        value: str,
    ) -> Entity | None:

        parsed = parse_wikilink(value)

        if parsed is None:
            return None

        entity_name, _display_name = parsed

        return self.db.scalar(
            select(Entity).where(
                ci_equals(Entity.name, entity_name)
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