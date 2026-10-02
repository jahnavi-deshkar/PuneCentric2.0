"""FastAPI application entry point for PuneCentric."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import health, routes, search

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(
    title="PuneCentric API",
    description="Pune multimodal route explorer API.",
    version="0.1.0",
)

# Keep API routes ahead of the catch-all frontend mount.
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(routes.router, prefix="/api", tags=["routes"])
app.include_router(search.router, prefix="/api", tags=["search"])

# Serves frontend/index.html at / and its CSS/JS assets from /css and /js.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
