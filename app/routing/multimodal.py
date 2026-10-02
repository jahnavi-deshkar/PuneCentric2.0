"""Unified multimodal candidate synthesis and ranking."""

from __future__ import annotations

import logging

from app.calculations.distance import haversine_distance_meters
from app.calculations.fares import FareEngine, fare_engine
from app.calculations.emissions import EmissionEngine, emission_engine
from app.models.route import LocationPoint, RouteLeg, RouteRequest, RouteResponse
from app.routing.candidates import CandidateGenerator, RouteCandidate
from app.routing.cache import route_cache_key, route_response_cache
from app.routing.constraints import ConstraintFilter, constraint_filter
from app.routing.pareto import ParetoOptimizer, pareto_optimizer
from app.transport.bus import BusRouter, bus_router
from app.transport.metro import MetroRouter, metro_router
from app.transport.walking import WalkingRouter, walking_router

LOGGER = logging.getLogger(__name__)
TRANSFER_WALK_LIMIT_METERS = 900.0
TRANSFER_PENALTY_MINUTES = 4.0


class MultimodalRouter:
    """Build reasonable distinct route options from the available transit networks."""

    def __init__(
        self,
        generator: CandidateGenerator | None = None,
        walking: WalkingRouter | None = None,
        bus: BusRouter | None = None,
        metro: MetroRouter | None = None,
        fares: FareEngine | None = None,
        emissions: EmissionEngine | None = None,
        constraints_filter: ConstraintFilter | None = None,
        optimizer: ParetoOptimizer | None = None,
    ) -> None:
        self.emissions = emissions or emission_engine
        self.generator = generator or CandidateGenerator(emissions=self.emissions)
        self.walking = walking or walking_router
        self.bus = bus or bus_router
        self.metro = metro or metro_router
        self.fares = fares or fare_engine
        self.constraints_filter = constraints_filter or constraint_filter
        self.optimizer = optimizer or pareto_optimizer

    def route(self, request: RouteRequest) -> list[RouteResponse]:
        """Return memoized choices for roughly 11-meter rounded coordinate cells."""
        constraints = request.constraints.model_dump(mode="json", exclude_none=True) if request.constraints else {}
        key = route_cache_key(
            f"multimodal:{id(self)}",
            request.origin,
            request.destination,
            {
                "constraints": constraints,
                "origin_label": request.origin.label,
                "destination_label": request.destination.label,
            },
        )
        return route_response_cache.get_or_compute(key, lambda: self._route_uncached(request))

    def _route_uncached(self, request: RouteRequest) -> list[RouteResponse]:
        candidates = self.generator.generate(request)
        candidates.extend(self._bus_metro_candidates(request))
        candidates = self._deduplicate(candidates)
        candidates = self._filter_inefficient_walks(candidates)
        candidates = self.constraints_filter.filter_candidates(candidates, request.constraints)
        # Pareto filtering removes options that are no better on any of the
        # four user-facing objectives; every remaining route is useful tradeoff.
        selected = self.optimizer.optimize(candidates)
        return [candidate.as_response() for candidate in selected]

    def _bus_metro_candidates(self, request: RouteRequest) -> list[RouteCandidate]:
        """Try one bus-to-metro transfer where a bus alighting stop meets a station."""
        if not self.metro.stations or not self.bus.routes:
            return []
        candidates: list[RouteCandidate] = []
        station_rows = list(self.metro.stations.values())
        transfer_pairs = []
        for bus_route in self.bus.routes:
            for stop in bus_route.stops:
                for station in station_rows:
                    gap = haversine_distance_meters((stop.lat, stop.lng), (station.lat, station.lng))
                    if gap <= TRANSFER_WALK_LIMIT_METERS:
                        transfer_pairs.append((gap, stop, station))
        # Bound the search: the seeded feed may repeat stops over outbound/return routes.
        seen_pairs: set[tuple[str, str]] = set()
        ordered_pairs = []
        for gap, stop, station in sorted(transfer_pairs, key=lambda row: row[0]):
            key = (stop.id, station.id)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            ordered_pairs.append((gap, stop, station))
        ordered_pairs = ordered_pairs[:20]

        for index, (gap_m, stop, station) in enumerate(ordered_pairs):
            transfer_point_bus = LocationPoint(lat=stop.lat, lng=stop.lng, label=stop.name)
            transfer_point_metro = LocationPoint(lat=station.lat, lng=station.lng, label=station.name)
            try:
                bus_response = self.bus.route(RouteRequest(origin=request.origin, destination=transfer_point_bus))
                bus_leg_index = next(i for i, leg in enumerate(bus_response.legs) if leg.mode == "bus")
                actual_alight = bus_response.legs[bus_leg_index].alight_stop
                if actual_alight is None or haversine_distance_meters(
                    (actual_alight.lat, actual_alight.lng), (station.lat, station.lng)
                ) > TRANSFER_WALK_LIMIT_METERS:
                    continue
                metro_response = self.metro.route(RouteRequest(origin=transfer_point_metro, destination=request.destination))
                metro_leg_index = next(i for i, leg in enumerate(metro_response.legs) if leg.mode == "metro")
                first_metro_leg = metro_response.legs[metro_leg_index]
                board_station = first_metro_leg.board_station
                if board_station is None or haversine_distance_meters(
                    (station.lat, station.lng), (board_station.lat, board_station.lng)
                ) > TRANSFER_WALK_LIMIT_METERS:
                    continue
            except (ValueError, StopIteration, IndexError) as exc:
                LOGGER.debug("Could not form bus-metro transfer at %s: %s", station.name, exc)
                continue

            bus_legs = bus_response.legs[: bus_leg_index + 1]
            metro_legs = metro_response.legs[metro_leg_index:]
            # Walk between the actual alighting point and the metro station. Four
            # extra minutes models interchange and wayfinding beyond walk speed.
            board_station = metro_legs[0].board_station
            assert board_station is not None
            walk_transfer = self.walking.route(RouteRequest(
                origin=LocationPoint(lat=actual_alight.lat, lng=actual_alight.lng, label=actual_alight.name),
                destination=LocationPoint(lat=board_station.lat, lng=board_station.lng, label=board_station.name),
            )).legs[0]
            legs = [
                *bus_legs,
                walk_transfer,
                RouteLeg(mode="transfer", distance_km=0.0, duration_min=TRANSFER_PENALTY_MINUTES,
                         fare_inr=0.0, geometry=[], transfer_station=board_station,
                         fare_breakdown=self.fares.zero("transfer"),
                         **self.emissions.leg_metrics("walking", 0.0)),
                *metro_legs,
            ]
            total_distance_km = round(sum(leg.distance_km for leg in legs), 3)
            route_environment = self.emissions.route_metrics(legs, total_distance_km)
            combined = RouteResponse(
                mode="multimodal",
                total_distance_km=total_distance_km,
                total_duration_min=round(sum(leg.duration_min for leg in legs), 1),
                total_fare_inr=round(sum(leg.fare_inr for leg in legs), 2),
                legs=legs,
                fare_breakdown=self.fares.combine(
                    [leg.fare_breakdown or self.fares.zero(leg.mode) for leg in legs], mode="multimodal"
                ),
                **route_environment,
            )
            candidates.append(RouteCandidate.from_response(
                combined,
                f"bus-metro-{index + 1}",
                f"Bus + Metro via {station.name}",
                self.emissions,
            ))
        return candidates

    @staticmethod
    def _deduplicate(candidates: list[RouteCandidate]) -> list[RouteCandidate]:
        unique: dict[tuple, RouteCandidate] = {}
        for candidate in candidates:
            transit_signature = tuple(
                (leg.mode, leg.route_name, leg.line_id,
                 getattr(leg.board_stop, "id", None), getattr(leg.alight_stop, "id", None),
                 getattr(leg.board_station, "id", None), getattr(leg.alight_station, "id", None))
                for leg in candidate.response.legs if leg.mode in {"bus", "metro", "auto"}
            )
            signature = (
                transit_signature,
                round(candidate.total_distance_km, 1),
                round(candidate.total_duration_min, 0),
                round(candidate.total_fare_inr, 0),
            )
            previous = unique.get(signature)
            if previous is None or candidate.total_duration_min < previous.total_duration_min:
                unique[signature] = candidate
        return list(unique.values())

    @staticmethod
    def _filter_inefficient_walks(candidates: list[RouteCandidate]) -> list[RouteCandidate]:
        if not candidates:
            return []
        non_walk = [candidate for candidate in candidates if any(
            leg.mode in {"bus", "metro", "auto"} for leg in candidate.response.legs
        )]
        if not non_walk:
            return candidates
        fastest_transit = min(candidate.total_duration_min for candidate in non_walk)
        return [candidate for candidate in candidates if not (
            all(leg.mode == "walking" for leg in candidate.response.legs)
            and candidate.walk_distance_km > 8.0
            and candidate.total_duration_min > fastest_transit * 1.35
        )]


multimodal_router = MultimodalRouter()
