"""Pydantic models for public-transit data and legs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BusStop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class BusRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: str
    route_name: str
    stops: list[BusStop]


class BusLeg(BaseModel):
    route_name: str
    board_stop: BusStop
    alight_stop: BusStop
    distance_km: float = Field(ge=0)
    duration_min: float = Field(ge=0)
    fare_inr: float = Field(ge=0)
    co2_grams: float = Field(ge=0)
    geometry: list[list[float]]


class MetroStation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class MetroLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: str
    line_name: str
    line_color: str
    route_sequence: list[str]


class MetroLeg(BaseModel):
    line_name: str
    line_color: str
    board_station: MetroStation
    alight_station: MetroStation
    distance_km: float = Field(ge=0)
    duration_min: float = Field(ge=0)
    fare_inr: float = Field(ge=0)
    co2_grams: float = Field(ge=0)
    geometry: list[list[float]]
