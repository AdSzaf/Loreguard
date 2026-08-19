from fastapi import FastAPI
from fastapi import Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine
from app.core.database import get_db
from app.core.vault_schema import VaultSchema
from app.models import Conflict, ConflictStatus, Document, Entity, Event, Fact
from app.services.consistency_engine import ConsistencyEngine
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.entity_indexer import EntityIndexer
from app.services.event_extractor import EventExtractor
from app.services.fact_extractor import FactExtractor
from app.services.markdown_parser import MarkdownParser
from app.services.vault_scanner import VaultScanner

app = FastAPI(
    title=settings.app_name,
    description="API for maintaining consistency of a fictional world.",
    version=settings.app_version,
)

# Local dev only: Vite (default port 5173) calling FastAPI (default
# port 8000) is a cross-origin request. No auth/session cookies are
# involved yet, so a permissive localhost allow-list is fine for now
# -- tighten this before ever exposing the API beyond localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "application": settings.app_name,
        "status": "running",
        "version": settings.app_version,
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "ok"
    }


@app.get("/api/health/database")
def database_health_check():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))

    return {
        "database": "connected",
        "result": result.scalar(),
    }

@app.get("/api/vault/scan")
def scan_vault():
    scanner = VaultScanner()

    files = scanner.scan_markdown_files()

    return {
        "files_found": len(files),
        "files": [
            str(file.relative_to(scanner.vault_path))
            for file in files
        ],
    }

@app.post("/api/vault/sync")
def sync_vault(
    db: Session = Depends(get_db),
):
    """
    Full sync pipeline for the vault:

        1. scan .md files
        2. sync Document rows (create/update by content hash)
        3. index entities referenced via [[wikilinks]]
        4. extract facts from frontmatter
        5. extract structured events from frontmatter

    Steps 3-5 need every Document to exist first (entities can
    reference documents that come later in the scan), so entities
    are indexed for all documents before facts/events are
    extracted for any of them.
    """

    scanner = VaultScanner()
    parser = MarkdownParser()
    schema = VaultSchema(scanner.vault_path)

    document_service = DocumentService(db)
    entity_indexer = EntityIndexer(db, schema)
    fact_extractor = FactExtractor(db)
    event_extractor = EventExtractor(db, schema)
    embedding_service = EmbeddingService(db)

    files = scanner.scan_markdown_files()

    synced: list[dict] = []

    for file_path in files:
        parsed_document = parser.parse(
            file_path=file_path,
            vault_path=scanner.vault_path,
        )

        document = document_service.sync_document(parsed_document)

        synced.append({
            "document": document,
            "parsed": parsed_document,
        })

    for entry in synced:
        entity_indexer.index_document(
            entry["document"],
            entry["parsed"].frontmatter,
        )

    db.commit()

    documents_summary = []

    for entry in synced:
        document = entry["document"]
        parsed_document = entry["parsed"]

        facts = fact_extractor.extract_from_document(
            document,
            parsed_document,
        )

        event = event_extractor.extract_from_document(
            document,
            parsed_document,
        )

        embedding_service.update_document_embedding(document)

        documents_summary.append({
            "id": document.id,
            "title": document.title,
            "path": document.path,
            "entities_linked": len(document.entities),
            "facts_extracted": len(facts),
            "is_event": event is not None,
        })

    db.commit()

    consistency_engine = ConsistencyEngine(db, schema=schema)
    conflict_summary = consistency_engine.run()
    db.commit()

    return {
        "files_found": len(files),
        "documents_synced": len(documents_summary),
        "documents": documents_summary,
        "conflicts": conflict_summary,
    }


@app.get("/api/events")
def list_events(
    db: Session = Depends(get_db),
):
    events = db.scalars(select(Event)).all()

    return [
        {
            "id": event.id,
            "name": event.entity.name,
            "date_text": event.date_text,
            "date_start_year": event.date_start_year,
            "date_end_year": event.date_end_year,
            "precision": event.precision,
            "location": event.location.name if event.location else None,
            "outcome": event.outcome,
            "participants": [
                {
                    "name": participant.entity.name,
                    "role": participant.role,
                }
                for participant in event.participants
            ],
            "source_document": event.document.title,
        }
        for event in events
    ]


@app.get("/api/conflicts")
def list_conflicts(
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(Conflict)

    if status:
        query = query.where(Conflict.status == ConflictStatus(status))

    conflicts = db.scalars(query).all()

    def describe_fact(fact) -> dict | None:
        if fact is None:
            return None

        return {
            "predicate": fact.predicate,
            "value": (
                fact.object_entity.name
                if fact.object_entity_id is not None and fact.object_entity
                else fact.object_value
            ),
            "source_document": fact.document.title,
        }

    return [
        {
            "id": conflict.id,
            "entity": conflict.entity.name,
            "rule_name": conflict.rule_name,
            "severity": conflict.severity,
            "confidence": conflict.confidence,
            "status": conflict.status,
            "explanation": conflict.explanation,
            "fact_a": describe_fact(conflict.fact_a),
            "fact_b": describe_fact(conflict.fact_b),
            "related_event": (
                conflict.related_event.entity.name
                if conflict.related_event
                else None
            ),
            "resolution_note": conflict.resolution_note,
        }
        for conflict in conflicts
    ]


@app.post("/api/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: int,
    status: str,
    resolution_note: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Records the person's decision on a conflict. LoreGuard never
    edits the vault itself -- this only updates LoreGuard's own
    record of what was decided (accept / dismiss / explain).
    """

    conflict = db.get(Conflict, conflict_id)

    if conflict is None:
        return {"error": "Conflict not found"}

    conflict.status = ConflictStatus(status)

    if resolution_note is not None:
        conflict.resolution_note = resolution_note

    db.commit()

    return {
        "id": conflict.id,
        "status": conflict.status,
        "resolution_note": conflict.resolution_note,
    }


@app.get("/api/documents")
def list_documents(
    db: Session = Depends(get_db),
):
    documents = db.scalars(select(Document)).all()

    return [
        {
            "id": document.id,
            "title": document.title,
            "path": document.path,
            "indexed_at": document.indexed_at,
            "file_modified_at": document.file_modified_at,
            "entities_linked": len(document.entities),
            "has_embedding": document.embedding is not None,
        }
        for document in documents
    ]


@app.get("/api/documents/{document_id}/similar")
def similar_documents(
    document_id: int,
    limit: int = 5,
    db: Session = Depends(get_db),
):
    """
    Documents most similar to this one by embedding cosine
    similarity (plan section 27: narrow the vault down to relevant
    documents before handing anything to an LLM). Currently backed
    by an offline placeholder embedding (see embedding_provider.py)
    -- similarity reflects shared vocabulary, not meaning, until a
    real provider is plugged in.
    """

    document = db.get(Document, document_id)

    if document is None:
        return {"error": "Document not found"}

    embedding_service = EmbeddingService(db)
    results = embedding_service.find_similar(document, limit=limit)

    return {
        "document": document.title,
        "similar": [
            {
                "id": similar_doc.id,
                "title": similar_doc.title,
                "similarity": round(score, 4),
            }
            for similar_doc, score in results
        ],
    }


@app.get("/api/entities")
def list_entities(
    entity_type: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(Entity)

    if entity_type:
        query = query.where(Entity.entity_type == entity_type)

    entities = db.scalars(query).all()

    return [
        {
            "id": entity.id,
            "name": entity.name,
            "entity_type": entity.entity_type,
            "aliases": [alias.alias for alias in entity.aliases],
            "documents": len(entity.documents),
        }
        for entity in entities
    ]


@app.get("/api/entities/{entity_id}")
def get_entity(
    entity_id: int,
    db: Session = Depends(get_db),
):
    """
    Full detail for one entity: its facts, the events it
    participates in, and any open conflicts about it -- the data
    behind a future EntityDetail / "Why?" view (plan section 32).
    """

    entity = db.get(Entity, entity_id)

    if entity is None:
        return {"error": "Entity not found"}

    facts_as_subject = db.scalars(
        select(Fact).where(Fact.subject_entity_id == entity_id)
    ).all()

    conflicts = db.scalars(
        select(Conflict).where(Conflict.entity_id == entity_id)
    ).all()

    return {
        "id": entity.id,
        "name": entity.name,
        "entity_type": entity.entity_type,
        "aliases": [alias.alias for alias in entity.aliases],
        "facts": [
            {
                "id": fact.id,
                "predicate": fact.predicate,
                "value": (
                    fact.object_entity.name
                    if fact.object_entity_id is not None
                    and fact.object_entity
                    else fact.object_value
                ),
                "source_document": fact.document.title,
            }
            for fact in facts_as_subject
        ],
        "conflicts": [
            {
                "id": conflict.id,
                "rule_name": conflict.rule_name,
                "status": conflict.status,
                "explanation": conflict.explanation,
            }
            for conflict in conflicts
        ],
    }


@app.get("/api/facts")
def list_facts(
    entity_id: int | None = None,
    predicate: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(Fact)

    if entity_id is not None:
        query = query.where(Fact.subject_entity_id == entity_id)

    if predicate is not None:
        query = query.where(Fact.predicate.ilike(predicate))

    facts = db.scalars(query).all()

    return [
        {
            "id": fact.id,
            "subject": fact.subject.name,
            "predicate": fact.predicate,
            "value": (
                fact.object_entity.name
                if fact.object_entity_id is not None and fact.object_entity
                else fact.object_value
            ),
            "source_document": fact.document.title,
        }
        for fact in facts
    ]


@app.get("/api/dashboard")
def dashboard(
    db: Session = Depends(get_db),
):
    """
    Summary counts for the main dashboard (plan section 19),
    including a simple "canon health" score: the share of tracked
    conflicts that are NOT open (resolved, dismissed, or explained).
    An empty vault or a vault with zero conflicts reads as 100%.
    """

    documents_count = db.query(Document).count()
    entities_count = db.query(Entity).count()
    facts_count = db.query(Fact).count()
    events_count = db.query(Event).count()

    conflicts_total = db.query(Conflict).count()
    conflicts_open = db.query(Conflict).filter(
        Conflict.status == ConflictStatus.OPEN
    ).count()

    canon_health = (
        100.0
        if conflicts_total == 0
        else round(
            100.0 * (conflicts_total - conflicts_open) / conflicts_total,
            1,
        )
    )

    open_conflicts_preview = db.scalars(
        select(Conflict)
        .where(Conflict.status == ConflictStatus.OPEN)
        .order_by(Conflict.severity.desc())
        .limit(5)
    ).all()

    return {
        "documents": documents_count,
        "entities": entities_count,
        "facts": facts_count,
        "events": events_count,
        "conflicts_total": conflicts_total,
        "conflicts_open": conflicts_open,
        "canon_health_percent": canon_health,
        "open_conflicts_preview": [
            {
                "id": conflict.id,
                "entity": conflict.entity.name,
                "severity": conflict.severity,
                "explanation": conflict.explanation,
            }
            for conflict in open_conflicts_preview
        ],
    }