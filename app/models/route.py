"""Pydantic request and response models for route planning."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class RouteResponse(BaseModel):
    mode: str
    total_distance_km: float = Field(ge=0)
    total_duration_min: float = Field(ge=0)
    total_fare_inr: float = Field(ge=0)
    total_co2_grams: float = Field(ge=0)
    legs: list[RouteLeg]
