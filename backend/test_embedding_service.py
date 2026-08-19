"""
Self-contained test for EmbeddingService / HashingEmbeddingProvider.

In-memory SQLite -- proves the JSON-backed EmbeddingVector column
works with zero Postgres extensions, which is the whole point of
not using pgvector's native type yet.

Run with:
    python test_embedding_service.py
"""

import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import Document
from app.services.embedding_provider import HashingEmbeddingProvider
from app.services.embedding_service import EmbeddingService


passed = 0
failed = 0


def check(label: str, condition: bool) -> None:
    global passed, failed

    if condition:
        passed += 1
        print(f"  OK   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}")


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    now = datetime.datetime.utcnow()
    embedding_service = EmbeddingService(db)

    print("=" * 60)
    print("CASE 1: embedding round-trips through the DB (no pgvector)")
    print("=" * 60)

    doc = Document(
        title="Lunaris",
        path="Bogowie/Lunaris.md",
        content="Lunaris jest boginią księżyca i nocy.",
        content_hash="h1",
        file_modified_at=now,
    )
    db.add(doc)
    db.flush()

    check("embedding is None before first computation", doc.embedding is None)

    embedding_service.update_document_embedding(doc)
    db.commit()

    check(
        "embedding has correct dimensionality after computation",
        doc.embedding is not None
        and len(doc.embedding) == HashingEmbeddingProvider.dimensions,
    )

    db.expire_all()
    reloaded = db.get(Document, doc.id)

    check(
        "embedding survives a round-trip through SQLite as JSON",
        reloaded.embedding is not None
        and len(reloaded.embedding) == HashingEmbeddingProvider.dimensions,
    )
    check(
        "embedding_updated_at was stamped",
        reloaded.embedding_updated_at is not None,
    )

    print()
    print("=" * 60)
    print("CASE 2: similar documents score higher than unrelated ones")
    print("=" * 60)

    related_doc = Document(
        title="Lunaris - legenda",
        path="Bogowie/Lunaris_legenda.md",
        content=(
            "Legenda o Lunaris, bogini księżyca. Opowiada o młodej "
            "damie wędrującej nocą w blasku księżyca."
        ),
        content_hash="h2",
        file_modified_at=now,
    )

    unrelated_doc = Document(
        title="Tranio Zorish",
        path="Postacie/Tranio_Zorish.md",
        content=(
            "Podróżnik, kartograf i żeglarz. Odkrywca nowego "
            "kontynentu na zachód od Isury."
        ),
        content_hash="h3",
        file_modified_at=now,
    )

    db.add_all([related_doc, unrelated_doc])
    db.flush()

    for d in (related_doc, unrelated_doc):
        embedding_service.update_document_embedding(d)

    db.commit()

    results = embedding_service.find_similar(reloaded, limit=5)

    check("find_similar returns both other documents", len(results) == 2)

    scores = {doc.title: score for doc, score in results}

    check(
        "the related (shared-vocabulary) document scores higher",
        scores.get("Lunaris - legenda", -1)
        > scores.get("Tranio Zorish", 2),
    )

    print(
        "  scores:",
        {title: round(score, 3) for title, score in scores.items()},
    )

    print()
    print("=" * 60)
    print("CASE 3: title alone is still embeddable even with no content")
    print("=" * 60)

    empty_doc = Document(
        title="Empty",
        path="Empty.md",
        content="",
        content_hash="h4",
        file_modified_at=now,
    )
    db.add(empty_doc)
    db.flush()

    embedding_service.update_document_embedding(empty_doc)
    db.commit()

    check(
        "document with empty content but a title still gets embedded",
        empty_doc.embedding is not None,
    )

    print()
    print("=" * 60)
    print("CASE 4: reembed_all recomputes every document")
    print("=" * 60)

    count = embedding_service.reembed_all()
    db.commit()

    check(
        "reembed_all touches all documents with content",
        count == 4,  # doc, related_doc, unrelated_doc, empty_doc
    )

    print()
    print("=" * 60)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 60)

    db.close()

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
