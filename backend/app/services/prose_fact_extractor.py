from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db_utils import ci_equals
from app.models import Document, Entity, EntityAlias, Fact
from app.services.llm_provider import LLMProvider, logger
from app.services.retry_utils import call_with_rate_limit_retry


class ProseFactExtractor:
    """
    Extracts facts from a document's BODY TEXT (Document.content is
    already frontmatter-stripped by MarkdownParser) using an
    LLMProvider, then resolves them against known entities and
    stores them as Facts with source_type="llm_prose".

    This is what unlocks the flagship scenario from the project
    concept: a character's death date, stated in prose across two
    different articles, ending up as two Facts with predicate
    "died" (or whatever word the author used) and different years
    -- which ExclusiveFactRule (already built, unchanged) then
    flags as a conflict.

    Design choices that matter:
      - subject/object are only resolved against entities that
        ALREADY EXIST (by name or alias). This extractor never
        creates new entities from LLM output -- an LLM inventing an
        entity that doesn't exist elsewhere in the vault is exactly
        the kind of ungrounded claim plan section 14 warns against.
        A candidate whose subject can't be resolved is dropped.
      - object is stored as a linked entity if it resolves to one,
        otherwise as plain text (object_value) -- same convention
        as FactExtractor, so ExclusiveFactRule/RelationshipContra-
        dictionRule work identically regardless of fact source.
      - idempotent per document: re-running replaces only this
        document's "llm_prose" facts, leaving frontmatter facts
        (owned by FactExtractor) untouched.
      - marks document.llm_facts_hash = document.content_hash on
        every successful pass (including "nothing to extract" for
        an empty document), and leaves it untouched if the LLM call
        raises. This is what lets a bulk/incremental run (see
        main.py's POST /api/vault/extract-llm-facts) skip documents
        that are already up to date and retry ones that failed.
    """

    def __init__(self, db: Session, provider: LLMProvider):
        self.db = db
        self.provider = provider

    def extract_from_document(self, document: Document) -> list[Fact]:
        text = (document.content or "").strip()

        if not text:
            # Nothing to extract, but this *is* a completed, valid
            # pass over the current content -- mark it processed so
            # a bulk run doesn't keep retrying an empty document
            # forever.
            document.llm_facts_hash = document.content_hash
            return []

        known_entity_names = [
            name
            for (name,) in self.db.execute(select(Entity.name)).all()
        ]

        candidates = call_with_rate_limit_retry(
            self.provider.extract_facts, text, known_entity_names,
        )

        self.db.query(Fact).filter(
            Fact.document_id == document.id,
            Fact.source_type == "llm_prose",
        ).delete(synchronize_session=False)

        facts: list[Fact] = []

        for candidate in candidates:
            subject = self._find_entity(candidate.subject)

            if subject is None:
                logger.info(
                    "Dropping LLM fact: subject %r not found among "
                    "known entities (predicate=%r, object=%r, "
                    "doc=%r). Add a note for this entity, or link it "
                    "elsewhere in the vault, so it gets indexed first.",
                    candidate.subject,
                    candidate.predicate,
                    candidate.object,
                    document.title,
                )
                continue

            object_entity = self._find_entity(candidate.object)

            fact = Fact(
                subject_entity_id=subject.id,
                predicate=candidate.predicate,
                object_entity_id=(
                    object_entity.id if object_entity else None
                ),
                object_value=(
                    None if object_entity else candidate.object
                ),
                object_number=candidate.object_number,
                document_id=document.id,
                source_type="llm_prose",
                confidence=max(0.0, min(1.0, candidate.confidence)),
                source_text=candidate.source_text or None,
            )

            self.db.add(fact)
            facts.append(fact)

        # Only reached if provider.extract_facts() didn't raise --
        # an exception propagates past this line, so a failed
        # extraction correctly leaves the hash stale/unset and gets
        # retried on the next bulk run instead of being marked done.
        document.llm_facts_hash = document.content_hash

        self.db.flush()

        return facts

    def _find_entity(self, name: str) -> Entity | None:
        if not name:
            return None

        entity = self.db.scalar(
            select(Entity).where(ci_equals(Entity.name, name))
        )

        if entity is not None:
            return entity

        return self.db.scalar(
            select(Entity)
            .join(EntityAlias)
            .where(ci_equals(EntityAlias.alias, name))
        )
