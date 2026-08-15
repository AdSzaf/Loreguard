from fastapi import FastAPI

app = FastAPI(
    title="LoreGuard API",
    description="API for maintaining consistency of a fictional world.",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "application": "LoreGuard",
        "status": "running",
        "version": "0.1.0",
    }