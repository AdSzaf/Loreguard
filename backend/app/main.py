from fastapi import FastAPI
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine
from app.core.database import get_db
from app.services.document_service import DocumentService
from app.services.markdown_parser import MarkdownParser
from app.services.vault_scanner import VaultScanner

app = FastAPI(
    title=settings.app_name,
    description="API for maintaining consistency of a fictional world.",
    version=settings.app_version,
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
    scanner = VaultScanner()
    parser = MarkdownParser()
    service = DocumentService(db)

    files = scanner.scan_markdown_files()

    synced_documents = []

    for file_path in files:
        parsed_document = parser.parse(
            file_path=file_path,
            vault_path=scanner.vault_path,
        )

        document = service.sync_document(parsed_document)

        synced_documents.append({
            "id": document.id,
            "title": document.title,
            "path": document.path,
        })

    return {
        "files_found": len(files),
        "documents_synced": len(synced_documents),
        "documents": synced_documents,
    }