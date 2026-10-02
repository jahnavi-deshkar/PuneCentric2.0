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
    constraints: "RouteConstraints | None" = None


class RouteConstraints(BaseModel):
    """Optional hard limits applied to multimodal route candidates."""

    model_config = ConfigDict(extra="forbid")

    max_budget_inr: float | None = Field(default=None, ge=0)
    max_walk_distance_km: float | None = Field(default=None, ge=0)
    max_transfers: int | None = Field(default=None, ge=0)


class FareBreakdown(BaseModel):
    """Normalized itemized fare returned by the centralized fare engine."""

    mode: str
    base_fare: float = Field(default=0, ge=0)
    distance_fare: float = Field(default=0, ge=0)
    surcharges: float = Field(default=0, ge=0)
    discounts: float = Field(default=0, ge=0)
    total_fare: float = Field(default=0, ge=0)
    currency: str = "INR"
    surcharge_details: dict[str, float] = Field(default_factory=dict)
    discount_details: dict[str, float] = Field(default_factory=dict)


class RouteLeg(BaseModel):
    mode: str
    distance_km: float = Field(ge=0)
    duration_min: float = Field(ge=0)
    fare_inr: float = Field(ge=0)
    co2_grams: float = Field(ge=0)
    co2_saved_grams: float = 0.0
    eco_badge: str | None = None
    trees_equivalent: float = Field(default=0, ge=0)
    smartphone_charges_equivalent: float = Field(default=0, ge=0)
    private_car_baseline_co2_grams: float = Field(default=0, ge=0)
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
    from_label: str | None = None
    to_label: str | None = None
    fare_breakdown: FareBreakdown | None = None


class RouteResponse(BaseModel):
    mode: str
    total_distance_km: float = Field(ge=0)
    total_duration_min: float = Field(ge=0)
    total_fare_inr: float = Field(ge=0)
    total_co2_grams: float = Field(ge=0)
    co2_grams: float = Field(default=0, ge=0)
    legs: list[RouteLeg]
    candidate_id: str | None = None
    candidate_name: str | None = None
    preference_tags: list[str] = Field(default_factory=list)
    transfers_count: int = Field(default=0, ge=0)
    walk_distance_km: float = Field(default=0, ge=0)
    fare_breakdown: FareBreakdown | None = None
    co2_saved_grams: float = 0.0
    eco_badge: str | None = None
    trees_equivalent: float = Field(default=0, ge=0)
    smartphone_charges_equivalent: float = Field(default=0, ge=0)
    private_car_baseline_co2_grams: float = Field(default=0, ge=0)
