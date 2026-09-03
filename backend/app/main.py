from fastapi import FastAPI
from fastapi import Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine
from app.core.database import get_db
from app.core.db_utils import ci_equals
from app.core.vault_schema import VaultSchema
from app.models import Conflict, ConflictStatus, Document, Entity, Event, Fact
from app.services.consistency_engine import ConsistencyEngine
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.entity_indexer import EntityIndexer
from app.services.event_extractor import EventExtractor
from app.services.fact_extractor import FactExtractor
from app.services.embedding_provider import get_embedding_provider
from app.services.llm_provider import get_llm_provider, logger
from app.services.semantic_conflict_service import SemanticConflictService
from app.services.markdown_parser import MarkdownParser
from app.services.prose_fact_extractor import ProseFactExtractor
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

    # Documents whose file disappeared from the vault (renamed,
    # moved outside, or deleted) get removed too -- Fact/Event/
    # DocumentEntity rows cascade automatically via their FKs.
    #
    # Safety: only ever runs when the scan actually found files.
    # If `files` is empty (e.g. a misconfigured or momentarily
    # unreachable OBSIDIAN_VAULT_PATH), skip deletion entirely --
    # otherwise a bad path could silently wipe the whole database.
    documents_deleted = 0

    if files:
        synced_ids = {entry["document"].id for entry in synced}

        stale_documents = db.scalars(
            select(Document).where(Document.id.not_in(synced_ids))
        ).all()

        for stale_document in stale_documents:
            db.delete(stale_document)

        documents_deleted = len(stale_documents)

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

        # Deliberately NOT computed here. Embeddings hit a real,
        # separate external API with its own rate limit -- this used
        # to run unconditionally for every synced document and a
        # single 429 would crash the *entire* sync (documents,
        # facts, events, everything), which is unacceptable for the
        # app's most important, most frequently run feature.
        #
        # Embeddings are opt-in and computed lazily instead, the
        # same way LLM extraction is: SemanticConflictService
        # computes a document's embedding on first use (see
        # check_document), so a rate limit there only affects that
        # one opt-in action, never a plain sync.

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
        "documents_deleted": documents_deleted,
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
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
):
    """
    Paginated, alphabetically sorted (by title, case-insensitive).
    Note: /api/vault/sync and /api/vault/extract-llm-facts query
    ALL documents directly, bypassing this endpoint entirely --
    pagination here is purely a listing/UI concern and never limits
    what sync or bulk LLM processing actually covers.
    """

    page = max(1, page)
    page_size = max(1, min(page_size, 200))

    total = db.scalar(select(func.count()).select_from(Document)) or 0

    documents = db.scalars(
        select(Document)
        .order_by(func.lower(Document.title))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": [
            {
                "id": document.id,
                "title": document.title,
                "path": document.path,
                "indexed_at": document.indexed_at,
                "file_modified_at": document.file_modified_at,
                "entities_linked": len(document.entities),
                "has_embedding": document.embedding is not None,
                "needs_llm_processing": (
                    document.llm_facts_hash != document.content_hash
                ),
                "needs_semantic_check": (
                    document.semantic_check_hash != document.content_hash
                ),
            }
            for document in documents
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


@app.get("/api/documents/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    """
    Full detail for one document: its facts (frontmatter + LLM
    prose, distinguished by source_type) and linked entities --
    the data behind DocumentDetailView, and a natural place to
    trigger LLM extraction from too (same endpoint the list view
    already uses).
    """

    document = db.get(Document, document_id)

    if document is None:
        return {"error": "Document not found"}

    facts = db.scalars(
        select(Fact).where(Fact.document_id == document_id)
    ).all()

    return {
        "id": document.id,
        "title": document.title,
        "path": document.path,
        "indexed_at": document.indexed_at,
        "file_modified_at": document.file_modified_at,
        "has_embedding": document.embedding is not None,
        "needs_llm_processing": (
            document.llm_facts_hash != document.content_hash
        ),
        "needs_semantic_check": (
            document.semantic_check_hash != document.content_hash
        ),
        "entities": [
            {
                "id": entity.id,
                "name": entity.name,
                "entity_type": entity.entity_type,
            }
            for entity in document.entities
        ],
        "facts": [
            {
                "id": fact.id,
                "subject": fact.subject.name,
                "predicate": fact.predicate,
                "value": (
                    fact.object_entity.name
                    if fact.object_entity_id is not None
                    and fact.object_entity
                    else fact.object_value
                ),
                "source_type": fact.source_type,
                "confidence": fact.confidence,
                "source_text": fact.source_text,
            }
            for fact in facts
        ],
    }


@app.post("/api/embeddings/reembed-all")
def reembed_all_documents(
    db: Session = Depends(get_db),
):
    """
    Recomputes every document's embedding with whatever provider is
    currently configured. Needed after switching providers (e.g.
    from the offline hashing placeholder to real Gemini embeddings)
    -- old and new vectors have different dimensions/meaning and
    are never comparable, so leftover old ones would just silently
    fail similarity checks (EmbeddingService.find_similar skips
    mismatched dimensions) rather than error, which is easy to miss.
    Run this once right after adding GEMINI_API_KEY.
    """

    embedding_service = EmbeddingService(db, get_embedding_provider(settings))
    count = embedding_service.reembed_all()
    db.commit()

    return {"documents_reembedded": count}


@app.get("/api/documents/{document_id}/similar")
def similar_documents(
    document_id: int,
    limit: int = 5,
    db: Session = Depends(get_db),
):
    """
    Documents most similar to this one by embedding cosine
    similarity (plan section 27: narrow the vault down to relevant
    documents before handing anything to an LLM). Real semantic
    embeddings when GEMINI_API_KEY is set (see get_embedding_provider),
    otherwise falls back to the offline vocabulary-overlap placeholder.
    """

    document = db.get(Document, document_id)

    if document is None:
        return {"error": "Document not found"}

    embedding_service = EmbeddingService(db, get_embedding_provider(settings))
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


@app.get("/api/llm/status")
def llm_status():
    """
    Which LLM provider (if any) is currently active, without
    making a real API call. Useful for confirming your .env is
    wired up correctly before spending a real request on it.
    """

    provider = get_llm_provider(settings)

    if provider is None:
        return {
            "active_provider": None,
            "anthropic_key_set": bool(settings.anthropic_api_key),
            "gemini_key_set": bool(settings.gemini_api_key),
        }

    return {
        "active_provider": type(provider).__name__,
        "model": getattr(provider, "model", None),
        "anthropic_key_set": bool(settings.anthropic_api_key),
        "gemini_key_set": bool(settings.gemini_api_key),
    }


@app.post("/api/vault/extract-llm-facts")
def extract_llm_facts_bulk(
    force: bool = False,
    db: Session = Depends(get_db),
):
    """
    Incremental, whole-vault LLM fact extraction: runs
    ProseFactExtractor on every document whose content has changed
    since the LLM last successfully processed it (tracked via
    Document.llm_facts_hash vs content_hash), skipping documents
    that are already up to date. Pass force=true to reprocess
    everything regardless (useful after a prompt change).

    One document failing (bad LLM response, transient API error,
    etc.) does not stop the batch -- each document gets its own
    try/commit/rollback, and every failure is collected into
    `failed` in the response instead of only showing up in server
    logs. This is the direct answer to "how do I know where it
    broke at 300 notes" -- you get a structured report back.

    Runs the consistency engine once at the end, after every
    document has been (re-)processed, rather than after each one --
    much cheaper than re-running it per document.
    """

    provider = get_llm_provider(settings)

    if provider is None:
        return {
            "error": (
                "No LLM provider configured. Set ANTHROPIC_API_KEY "
                "and/or GEMINI_API_KEY in your .env to enable LLM "
                "fact extraction."
            )
        }

    documents = db.scalars(select(Document)).all()
    prose_extractor = ProseFactExtractor(db, provider)

    to_process = [
        document
        for document in documents
        if force or document.llm_facts_hash != document.content_hash
    ]

    processed = 0
    failed: list[dict] = []

    for document in to_process:
        try:
            prose_extractor.extract_from_document(document)
            db.commit()
            processed += 1
        except Exception as exc:  # noqa: BLE001 -- deliberately broad,
            # a single document's failure (bad LLM response, network
            # blip, rate limit) must never abort the whole batch.
            db.rollback()
            failed.append({
                "document_id": document.id,
                "document": document.title,
                "error": str(exc),
            })
            logger.warning(
                "LLM extraction failed for document %r (id=%s): %s",
                document.title, document.id, exc,
            )

    scanner = VaultScanner()
    schema = VaultSchema(scanner.vault_path)
    conflict_summary = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    return {
        "documents_total": len(documents),
        "processed": processed,
        "skipped_up_to_date": len(documents) - len(to_process),
        "failed": failed,
        "conflicts": conflict_summary,
    }


@app.post("/api/documents/{document_id}/extract-llm-facts")
def extract_llm_facts(
    document_id: int,
    db: Session = Depends(get_db),
):
    """
    Runs LLM-based fact extraction on this document's BODY TEXT
    (frontmatter facts are handled separately by /api/vault/sync,
    which never calls an LLM). This is intentionally a separate,
    opt-in, per-document endpoint rather than part of the regular
    sync: it costs a real API call and money, and per plan section
    14 the LLM should never run silently as "the truth" -- the
    person decides when and where to invoke it.

    After extraction, re-runs the consistency engine so any new
    conflicts (e.g. contradicting death dates across two articles)
    show up immediately in /api/conflicts.

    Requires ANTHROPIC_API_KEY or GEMINI_API_KEY to be set (see
    LLM_PROVIDER in .env for which one wins if both are); returns a
    clear error otherwise rather than failing with a confusing
    stack trace.
    """

    document = db.get(Document, document_id)

    if document is None:
        return {"error": "Document not found"}

    provider = get_llm_provider(settings)

    if provider is None:
        return {
            "error": (
                "No LLM provider configured. Set ANTHROPIC_API_KEY "
                "and/or GEMINI_API_KEY in your .env to enable LLM "
                "fact extraction."
            )
        }

    prose_extractor = ProseFactExtractor(db, provider)

    facts = prose_extractor.extract_from_document(document)
    db.commit()

    scanner = VaultScanner()
    schema = VaultSchema(scanner.vault_path)
    conflict_summary = ConsistencyEngine(db, schema=schema).run()
    db.commit()

    return {
        "document": document.title,
        "facts_extracted": len(facts),
        "facts": [
            {
                "predicate": fact.predicate,
                "value": (
                    fact.object_entity.name
                    if fact.object_entity_id is not None
                    and fact.object_entity
                    else fact.object_value
                ),
                "confidence": fact.confidence,
                "source_text": fact.source_text,
            }
            for fact in facts
        ],
        "conflicts": conflict_summary,
    }


@app.post("/api/documents/{document_id}/check-semantic-conflicts")
def check_semantic_conflicts(
    document_id: int,
    db: Session = Depends(get_db),
):
    """
    Finds contradictions between this document and topically
    similar ones -- worded completely differently, but describing
    the same underlying claim (plan section 6/13, the plague-death-
    toll example). Embeddings narrow the field first (cheap), the
    LLM only judges the narrowed-down candidates (the actual cost).

    Requires an embedding is computed first (done automatically if
    missing) and a real embedding provider (GEMINI_API_KEY) for
    genuinely semantic results -- without it, similarity falls back
    to shared-vocabulary matching, which finds far fewer real pairs.
    """

    document = db.get(Document, document_id)

    if document is None:
        return {"error": "Document not found"}

    provider = get_llm_provider(settings)

    if provider is None:
        return {
            "error": (
                "No LLM provider configured. Set ANTHROPIC_API_KEY "
                "and/or GEMINI_API_KEY in your .env to enable "
                "semantic conflict checking."
            )
        }

    embedding_service = EmbeddingService(db, get_embedding_provider(settings))
    service = SemanticConflictService(db, provider, embedding_service)

    try:
        result = service.check_document(document)
        db.commit()
    except Exception as exc:  # noqa: BLE001 -- external API call
        # (embeddings or LLM), e.g. a rate limit -- must return a
        # clean error, not a raw 500 (which can also confuse the
        # browser into reporting a misleading CORS error instead of
        # the real cause).
        db.rollback()
        logger.warning(
            "Semantic check failed for document %r (id=%s): %s",
            document.title, document.id, exc,
        )
        return {
            "document": document.title,
            "error": f"Sprawdzenie semantyczne nie powiodło się: {exc}",
        }

    return {"document": document.title, **result}


@app.post("/api/vault/check-semantic-conflicts")
def check_semantic_conflicts_bulk(
    force: bool = False,
    db: Session = Depends(get_db),
):
    """
    Incremental, whole-vault semantic conflict checking -- same
    pattern as /api/vault/extract-llm-facts: only documents whose
    content changed since their last check are processed (tracked
    via Document.semantic_check_hash), one document's failure
    doesn't abort the batch, and every failure is collected into
    `failed` instead of only showing up in server logs.
    """

    provider = get_llm_provider(settings)

    if provider is None:
        return {
            "error": (
                "No LLM provider configured. Set ANTHROPIC_API_KEY "
                "and/or GEMINI_API_KEY in your .env to enable "
                "semantic conflict checking."
            )
        }

    embedding_service = EmbeddingService(db, get_embedding_provider(settings))
    service = SemanticConflictService(db, provider, embedding_service)

    documents = db.scalars(select(Document)).all()

    to_process = [
        document
        for document in documents
        if force or document.semantic_check_hash != document.content_hash
    ]

    processed = 0
    total_conflicts = 0
    failed: list[dict] = []

    for document in to_process:
        try:
            result = service.check_document(document)
            db.commit()
            processed += 1
            total_conflicts += result.get("conflicts_found", 0)
        except Exception as exc:  # noqa: BLE001 -- one document's
            # failure (bad LLM response, rate limit, network blip)
            # must never abort the whole batch.
            db.rollback()
            failed.append({
                "document_id": document.id,
                "document": document.title,
                "error": str(exc),
            })
            logger.warning(
                "Semantic check failed for document %r (id=%s): %s",
                document.title, document.id, exc,
            )

    return {
        "documents_total": len(documents),
        "processed": processed,
        "skipped_up_to_date": len(documents) - len(to_process),
        "conflicts_found": total_conflicts,
        "failed": failed,
    }


@app.get("/api/entities")
def list_entities(
    entity_type: str | None = None,
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
):
    page = max(1, page)
    page_size = max(1, min(page_size, 200))

    base_query = select(Entity)
    count_query = select(func.count()).select_from(Entity)

    if entity_type:
        base_query = base_query.where(Entity.entity_type == entity_type)
        count_query = count_query.where(Entity.entity_type == entity_type)

    total = db.scalar(count_query) or 0

    entities = db.scalars(
        base_query
        .order_by(func.lower(Entity.name))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": [
            {
                "id": entity.id,
                "name": entity.name,
                "entity_type": entity.entity_type,
                "aliases": [alias.alias for alias in entity.aliases],
                "documents": len(entity.documents),
            }
            for entity in entities
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


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
        query = query.where(ci_equals(Fact.predicate, predicate))

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