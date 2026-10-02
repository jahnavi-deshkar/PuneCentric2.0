"""Generate, normalize, rank, and deduplicate route candidates."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.calculations.fares import fare_engine
from app.models.route import RouteLeg, RouteRequest, RouteResponse
from app.transport.auto import AutoRouter, auto_router
from app.transport.bus import BusRouter, bus_router
from app.transport.metro import MetroRouter, metro_router
from app.transport.walking import WalkingRouter, walking_router

LOGGER = logging.getLogger(__name__)
TRANSIT_MODES = {"bus", "metro", "auto"}
MODE_CHANGE_PENALTY_MINUTES = 4.0


@dataclass(frozen=True)
class RouteCandidate:
    """A response plus the common metrics used to compare journeys."""

    candidate_id: str
    candidate_name: str
    response: RouteResponse
    total_distance_km: float
    total_duration_min: float
    total_fare_inr: float
    total_co2_grams: float
    transfers_count: int
    walk_distance_km: float

    @classmethod
    def from_response(
        cls, response: RouteResponse, candidate_id: str, candidate_name: str
    ) -> "RouteCandidate":
        legs = response.legs
        walk_distance = sum(leg.distance_km for leg in legs if leg.mode == "walking")
        vehicle_modes = [leg.mode for leg in legs if leg.mode in TRANSIT_MODES]
        changes = sum(first != second for first, second in zip(vehicle_modes, vehicle_modes[1:]))
        explicit_transfers = sum(leg.mode == "transfer" for leg in legs)
        changes = max(changes, explicit_transfers)
        fare_summary = fare_engine.combine(
            [leg.fare_breakdown or fare_engine.zero(leg.mode) for leg in legs], mode="multimodal"
        )
        normalized = response.model_copy(update={
            "mode": "multimodal",
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "transfers_count": changes,
            "walk_distance_km": round(walk_distance, 3),
            "fare_breakdown": fare_summary,
        })
        return cls(
            candidate_id=candidate_id,
            candidate_name=candidate_name,
            response=normalized,
            total_distance_km=normalized.total_distance_km,
            total_duration_min=normalized.total_duration_min,
            total_fare_inr=normalized.total_fare_inr,
            total_co2_grams=normalized.total_co2_grams,
            transfers_count=changes,
            walk_distance_km=round(walk_distance, 3),
        )

    def as_response(self) -> RouteResponse:
        return self.response


class CandidateGenerator:
    """Ask the existing mode routers for usable journey options."""

    def __init__(
        self,
        walking: WalkingRouter | None = None,
        bus: BusRouter | None = None,
        metro: MetroRouter | None = None,
        auto: AutoRouter | None = None,
    ) -> None:
        self.walking = walking or walking_router
        self.bus = bus or bus_router
        self.metro = metro or metro_router
        self.auto = auto or auto_router

    def generate(self, request: RouteRequest) -> list[RouteCandidate]:
        candidates: list[RouteCandidate] = []
        try:
            candidates.append(RouteCandidate.from_response(
                self.walking.route(request), "walking-direct", "Direct walk"
            ))
        except (ValueError, RuntimeError) as exc:
            LOGGER.info("Walking candidate unavailable: %s", exc)

        for mode, router, title in (
            ("auto", self.auto, "Direct auto-rickshaw"),
            ("bus", self.bus, "Bus journey"),
            ("metro", self.metro, "Metro journey"),
        ):
            try:
                response = router.route(request)
                candidates.append(RouteCandidate.from_response(response, f"{mode}-direct", title))
                if mode in {"bus", "metro"}:
                    candidates.extend(self._connector_variants(response, mode, request))
            except (ValueError, RuntimeError) as exc:
                LOGGER.info("%s candidate unavailable: %s", mode, exc)
        return candidates

    def _connector_variants(self, response: RouteResponse, mode: str, request: RouteRequest) -> list[RouteCandidate]:
        """Replace long transit access/egress walks with auto connectors."""
        walk_positions = [index for index, leg in enumerate(response.legs) if leg.mode == "walking"]
        if not walk_positions:
            return []
        transit_title = "Bus" if mode == "bus" else "Metro"
        variants: list[RouteCandidate] = []
        first = walk_positions[0]
        last = walk_positions[-1]
        options: list[tuple[bool, bool]] = []
        if response.legs[first].distance_km > 0.8:
            options.append((True, False))
        if last != first and response.legs[last].distance_km > 0.8:
            options.append((False, True))
        if first != last and response.legs[first].distance_km > 0.8 and response.legs[last].distance_km > 0.8:
            options.append((True, True))

        for index, (use_first, use_last) in enumerate(options, start=1):
            legs = list(response.legs)
            try:
                if use_first:
                    old = legs[first]
                    origin_point = request.origin.model_copy()
                    connector = self.auto.get_first_mile_auto(
                        origin_point,
                        self._point_from_leg_stop(response, "board"),
                    )
                    # Existing router's access geometry runs origin -> boarding
                    # point. Preserve its endpoints and replace only its mode.
                    if connector is not None:
                        legs[first] = connector
                if use_last:
                    old = legs[last]
                    destination_point = request.destination.model_copy()
                    connector = self.auto.get_last_mile_auto(
                        self._point_from_leg_stop(response, "alight"),
                        destination_point,
                    )
                    if connector is not None:
                        legs[last] = connector
            except (ValueError, IndexError, TypeError, AttributeError) as exc:
                LOGGER.debug("Could not create %s auto connector: %s", mode, exc)
                continue
            # Account for pickup/boarding transitions where an auto leg meets
            # fixed-route transit, and for the reverse transition on egress.
            transfer_leg = RouteLeg(
                mode="transfer", distance_km=0.0,
                duration_min=MODE_CHANGE_PENALTY_MINUTES,
                fare_inr=0.0, co2_grams=0.0, geometry=[],
            )
            if use_last:
                legs.insert(last, transfer_leg)
            if use_first:
                legs.insert(first + 1, transfer_leg)
            variants.append(RouteCandidate.from_response(
                self._sum_legs(response.mode, legs),
                f"{mode}-auto-connector-{index}",
                f"Auto + {transit_title}" if use_first and not use_last else
                f"{transit_title} + auto" if use_last and not use_first else
                f"Auto + {transit_title} + auto",
            ))
        return variants

    @staticmethod
    def _point_from_leg_stop(response: RouteResponse, side: str):
        from app.models.route import LocationPoint

        transit = next((leg for leg in response.legs if leg.mode in {"bus", "metro"}), None)
        if transit is None:
            raise ValueError("Transit leg missing")
        stop = transit.board_stop if side == "board" else transit.alight_stop
        if stop is not None:
            return LocationPoint(lat=stop.lat, lng=stop.lng, label=stop.name)
        station = transit.board_station if side == "board" else transit.alight_station
        if station is not None:
            return LocationPoint(lat=station.lat, lng=station.lng, label=station.name)
        raise ValueError("Transit stop/station missing")

    @staticmethod
    def _sum_legs(mode: str, legs: list[RouteLeg]) -> RouteResponse:
        return RouteResponse(
            mode=mode,
            total_distance_km=round(sum(leg.distance_km for leg in legs), 3),
            total_duration_min=round(sum(leg.duration_min for leg in legs), 1),
            total_fare_inr=round(sum(leg.fare_inr for leg in legs), 2),
            total_co2_grams=round(sum(leg.co2_grams for leg in legs), 1),
            legs=legs,
            fare_breakdown=fare_engine.combine(
                [leg.fare_breakdown or fare_engine.zero(leg.mode) for leg in legs], mode=mode
            ),
        )
