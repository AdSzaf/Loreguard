from fastapi import FastAPI

from app.core.config import settings


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