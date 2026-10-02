"""Route-planning API endpoints."""

from fastapi import APIRouter

from app.models.route import RouteRequest, RouteResponse
from app.transport.walking import walking_router

router = APIRouter()


@router.post("/routes/walking", response_model=RouteResponse)
def walking_route(request: RouteRequest) -> RouteResponse:
    """Calculate a pedestrian route between the supplied coordinates."""
    return walking_router.route(request)
