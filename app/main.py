"""FastAPI application entry point for PuneCentric."""

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import health, routes, search

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PUBLIC_DATA_DIR = PROJECT_ROOT / "public" / "data"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
LOGGER = logging.getLogger(__name__)


def _configured_origins() -> list[str]:
    """Combine explicit production origins with local and Vercel deployment URLs."""
    origins = {
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    }
    for value in os.getenv("PUNECENTRIC_CORS_ORIGINS", "").split(","):
        origin = value.strip().rstrip("/")
        if origin:
            origins.add(origin)
    for key in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        host = os.getenv(key, "").strip().strip("/")
        if host:
            origins.add(host if host.startswith(("http://", "https://")) else f"https://{host}")
    return sorted(origins)

app = FastAPI(
    title="PuneCentric API",
    description="Pune multimodal route explorer API.",
    version="0.1.0",
)

# Vercel deploy URLs are generated per preview. A custom production domain can
# be added through PUNECENTRIC_CORS_ORIGINS without a code change. Credentials
# remain disabled because the API does not use cookie-based authentication.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_configured_origins(),
    allow_origin_regex=r"^https://[a-zA-Z0-9-]+\.vercel\.app$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keep API routes ahead of the catch-all frontend mount.
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(routes.router, prefix="/api", tags=["routes"])
app.include_router(search.router, prefix="/api", tags=["search"])

# All application data paths are resolved relative to this file, never the
# serverless process working directory. Routers load portable JSON datasets;
# optional/corrupt spatial index artifacts fall back to in-memory indexes.
# check_dir=False keeps a cold start alive if a deployment accidentally omits
# frontend files, so health/API routes can still report the deployment issue.
if not DATA_DIR.is_dir():
    LOGGER.warning("Data directory is absent from deployment bundle: %s", DATA_DIR)
if not FRONTEND_DIR.is_dir():
    LOGGER.warning("Frontend directory is absent from deployment bundle: %s", FRONTEND_DIR)
if not PUBLIC_DATA_DIR.is_dir():
    LOGGER.warning("Packaged static data directory is absent: %s", PUBLIC_DATA_DIR)

# Processed datasets are copied here by scripts/build_static_data.py. Mounting
# the deployment-ready copies separately keeps them available under /data/...;
# Vercel can promote these StaticFiles mounts to its CDN (see pyproject.toml).
app.mount(
    "/data",
    StaticFiles(directory=str(PUBLIC_DATA_DIR), check_dir=False),
    name="static-data",
)

# Serves frontend/index.html at / and its CSS/JS assets from /css and /js.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True, check_dir=False), name="frontend")
