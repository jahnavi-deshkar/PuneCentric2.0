"""Pydantic request and response models for route planning."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from app.models.transit import BusStop, MetroStation


class LocationPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    label: str | None = None


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: LocationPoint
    destination: LocationPoint


class RouteLeg(BaseModel):
    mode: str
    distance_km: float = Field(ge=0)
    duration_min: float = Field(ge=0)
    fare_inr: float = Field(ge=0)
    co2_grams: float = Field(ge=0)
    geometry: list[list[float]]
    route_name: str | None = None
    board_stop: BusStop | None = None
    alight_stop: BusStop | None = None
    line_id: str | None = None
    line_name: str | None = None
    line_color: str | None = None
    board_station: MetroStation | None = None
    alight_station: MetroStation | None = None
    transfer_station: MetroStation | None = None
    # Auto fare components are populated only for auto-rickshaw legs.
    fare_base_inr: float | None = Field(default=None, ge=0)
    fare_distance_inr: float | None = Field(default=None, ge=0)
    fare_night_surcharge_inr: float | None = Field(default=None, ge=0)
    fare_rate_per_km: float | None = Field(default=None, ge=0)
    night_surcharge_applied: bool = False
    fare_currency: str | None = None


class RouteResponse(BaseModel):
    mode: str
    total_distance_km: float = Field(ge=0)
    total_duration_min: float = Field(ge=0)
    total_fare_inr: float = Field(ge=0)
    total_co2_grams: float = Field(ge=0)
    legs: list[RouteLeg]
