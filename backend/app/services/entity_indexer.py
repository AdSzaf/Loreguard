from sqlalchemy.orm import Session

from app.core.vault_schema import VaultSchema
from app.models.document import Document
from app.services.entity_extractor import EntityExtractor
from app.services.entity_resolver import EntityResolver


class EntityIndexer:
    """
    Builds the Entity index from documents.

    Pipeline:

        Document
            ↓
        EntityExtractor (wikilinks in content)
            ↓
        EntityCandidate
            ↓
        EntityResolver
            ↓
        Entity
            ↓
        Document ↔ Entity

    Also ensures every document has its own "subject" entity
    (keyed by title), regardless of whether anything else in the
    vault links to it yet -- see EntityResolver.resolve_subject.
    """

    def __init__(self, db: Session, schema: VaultSchema):
        self.db = db
        self.schema = schema
        self.extractor = EntityExtractor()
        self.resolver = EntityResolver(db, schema)

    def index_document(
        self,
        document: Document,
        frontmatter: dict | None = None,
    ) -> int:
        """
        Extract and resolve entities referenced by a document, and
        ensure the document's own subject entity exists.

        Returns the number of unique entity references found in
        the document's content (not counting the subject entity).
        """

        subject = self.resolver.resolve_subject(
            document,
            frontmatter or {},
        )

        if subject not in document.entities:
            document.entities.append(subject)

        if not document.content:
            return 0

        candidates = self.extractor.extract_from_content(
            document.content
        )

        resolved_count = 0

        for candidate in candidates:
            entity = self.resolver.resolve(candidate)

            if entity not in document.entities:
                document.entities.append(entity)

            resolved_count += 1

        return resolved_count

    def index_all(self) -> dict:
        """
        Index entities for all documents.

        Returns basic indexing statistics.
        """

        documents = self.db.query(Document).all()

        total_references = 0
        indexed_documents = 0

        for document in documents:
            count = self.index_document(document)

            total_references += count
            indexed_documents += 1

        self.db.commit()

        return {
            "documents": indexed_documents,
            "entity_references": total_references,
        }