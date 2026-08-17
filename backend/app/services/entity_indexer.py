from sqlalchemy.orm import Session

from app.models.document import Document
from app.services.entity_extractor import EntityExtractor
from app.services.entity_resolver import EntityResolver


class EntityIndexer:
    """
    Builds the Entity index from documents.

    Pipeline:

        Document
            ↓
        EntityExtractor
            ↓
        EntityCandidate
            ↓
        EntityResolver
            ↓
        Entity
            ↓
        Document ↔ Entity
    """

    def __init__(self, db: Session):
        self.db = db
        self.extractor = EntityExtractor()
        self.resolver = EntityResolver(db)

    def index_document(self, document: Document) -> int:
        """
        Extract and resolve entities referenced by a document.

        Returns the number of unique entity references found.
        """

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