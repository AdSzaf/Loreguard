from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.schemas.document import ParsedDocument


class DocumentService:
    def __init__(self, db: Session):
        self.db = db

    def sync_document(
        self,
        parsed_document: ParsedDocument,
    ) -> Document:
        statement = select(Document).where(
            Document.path == parsed_document.path
        )

        document = self.db.scalar(statement)

        if document is None:
            document = Document(
                title=parsed_document.title,
                path=parsed_document.path,
                content=parsed_document.content,
                content_hash=parsed_document.content_hash,
                file_modified_at=parsed_document.file_modified_at,
                indexed_at=datetime.utcnow(),
            )

            self.db.add(document)
            self.db.commit()
            self.db.refresh(document)

            return document

        if document.content_hash == parsed_document.content_hash:
            return document

        document.title = parsed_document.title
        document.content = parsed_document.content
        document.content_hash = parsed_document.content_hash
        document.file_modified_at = parsed_document.file_modified_at
        document.updated_at = datetime.utcnow()
        document.indexed_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(document)

        return document