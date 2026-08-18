import os
from pathlib import Path
from dotenv import load_dotenv

from app.core.database import SessionLocal
from app.models import Document, Entity, Fact
from app.services.fact_extractor import FactExtractor
from app.services.markdown_parser import MarkdownParser

load_dotenv()
vault_path_env = os.getenv("OBSIDIAN_VAULT_PATH")
if vault_path_env:
    VAULT_PATH = Path(vault_path_env)
else:
    raise ValueError("Brak zmiennej OBSIDIAN_VAULT_PATH w pliku .env")


def main():
    db = SessionLocal()

    try:
        parser = MarkdownParser()
        extractor = FactExtractor(db)

        document = (
            db.query(Document)
            .filter(Document.title == "Tranio Zorish")
            .first()
        )

        if document is None:
            print("Document 'Tranio Zorish' not found.")
            return

        file_path = VAULT_PATH / document.path

        parsed_document = parser.parse(
            file_path=file_path,
            vault_path=VAULT_PATH,
        )

        print("=" * 60)
        print("EXTRACTING FACTS")
        print("=" * 60)

        facts = extractor.extract_from_document(
            document,
            parsed_document,
        )

        db.commit()

        print(f"\nCreated facts: {len(facts)}\n")

        for fact in facts:
            if fact.object_entity_id is not None:
                object_entity = db.get(
                    Entity,
                    fact.object_entity_id,
                )

                object_display = (
                    f"ENTITY:{object_entity.name}"
                    if object_entity
                    else "ENTITY:UNKNOWN"
                )
            else:
                object_display = fact.object_value

            print(
                f"{fact.subject.name} "
                f"-- {fact.predicate} --> "
                f"{object_display}"
            )

        print("\n=== Testing entity reference ===")

        test_value = "[[Naumir|Naumira]]"

        entity = extractor._resolve_wikilink_entity(test_value)

        if entity:
            print(
                f"Resolved: {test_value} -> "
                f"{entity.name} (ID: {entity.id})"
            )
        else:
            print("FAILED: entity reference was not resolved")

    finally:
        db.close()


if __name__ == "__main__":
    main()


