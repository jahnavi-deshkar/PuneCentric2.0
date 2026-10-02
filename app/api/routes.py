"""Route-planning API endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.models.route import RouteRequest, RouteResponse
from app.routing.multimodal import multimodal_router
from app.transport.bus import bus_router
from app.transport.auto import auto_router
from app.transport.metro import metro_router
from app.transport.walking import walking_router

router = APIRouter()


@router.post("/routes/multimodal", response_model=list[RouteResponse])
def multimodal_route(request: RouteRequest) -> list[RouteResponse]:
    """Return ranked walking, auto, bus, metro, and composite route choices."""
    return multimodal_router.route(request)


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


@router.post("/routes/auto", response_model=RouteResponse)
def auto_route(
    request: RouteRequest,
    night_surcharge: bool | None = Query(
        default=None,
        description="Override night pricing; omitted means apply it automatically from 00:00–05:00 Pune time.",
    ),
) -> RouteResponse:
    """Calculate a direct auto-rickshaw route and fare estimate."""
    try:
        return auto_router.route(request, night_surcharge=night_surcharge)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
