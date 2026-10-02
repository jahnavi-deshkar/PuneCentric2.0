"""Route-planning API endpoints."""

from fastapi import APIRouter, HTTPException

from app.models.route import RouteRequest, RouteResponse
from app.transport.bus import bus_router
from app.transport.metro import metro_router
from app.transport.walking import walking_router

router = APIRouter()


@router.post("/routes/walking", response_model=RouteResponse)
def walking_route(request: RouteRequest) -> RouteResponse:
    """Calculate a pedestrian route between the supplied coordinates."""
    return walking_router.route(request)


@router.post("/routes/bus", response_model=RouteResponse)
def bus_route(request: RouteRequest) -> RouteResponse:
    """Find a PMPML bus journey with walking access and egress legs."""
    try:
        return bus_router.route(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/routes/metro", response_model=RouteResponse)
def metro_route(request: RouteRequest) -> RouteResponse:
    """Find a Pune Metro trip, including Civil Court transfers when needed."""
    try:
        return metro_router.route(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
