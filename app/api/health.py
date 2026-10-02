"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Return the service health and configured city."""
    return {"status": "healthy", "city": "Pune"}
