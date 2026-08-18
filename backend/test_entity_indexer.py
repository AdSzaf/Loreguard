from app.core.config import settings
from app.core.database import SessionLocal
from app.core.vault_schema import VaultSchema
from app.models.document import Document
from app.services.entity_indexer import EntityIndexer


def main():
    db = SessionLocal()

    try:
        schema = VaultSchema(settings.obsidian_vault_path)
        indexer = EntityIndexer(db, schema)

        print("=" * 60)
        print("INDEXING ENTITIES")
        print("=" * 60)

        result = indexer.index_all()

        print()
        print("=" * 60)
        print("RESULT")
        print("=" * 60)

        print(f"Documents processed: {result['documents']}")
        print(f"Entity references:   {result['entity_references']}")

        print()
        print("=" * 60)
        print("DOCUMENT ENTITY COUNTS")
        print("=" * 60)

        documents = db.query(Document).all()

        for document in documents:
            print(
                f"{document.title}: "
                f"{len(document.entities)} entities"
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()