"""Direct auto-rickshaw routing and reusable first/last-mile connectors.

When a locally prepared OSMnx *drive* graph is present the router follows its
road network. In its absence it returns a clearly approximate, gently winding
geometry so offline development remains usable; this fallback is not a road
network route and should not be treated as navigation guidance.
"""

from __future__ import annotations

import logging
from pathlib import Path

import networkx as nx

from app.calculations.distance import haversine_distance_meters, polyline_distance_meters
from app.calculations.fares import FareEngine, fare_engine
from app.calculations.emissions import EmissionEngine, emission_engine
from app.models.route import LocationPoint, RouteLeg, RouteRequest, RouteResponse
from app.transport.walking import WalkingRouter, walking_router

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DRIVING_GRAPH_PATHS = (
    PROJECT_ROOT / "data" / "processed" / "pune_drive.graphml",
    PROJECT_ROOT / "data" / "processed" / "pune_roads.graphml",
    PROJECT_ROOT / "data" / "processed" / "driving_graph.graphml",
)

AVERAGE_SPEED_KMH = 25.0
CONNECTOR_WALK_THRESHOLD_METERS = 800.0


class AutoRouter:
    """Route autos over an available OSMnx driving graph, with offline fallback."""

    def __init__(self, graph: nx.Graph | None = None, graph_path: Path | str | None = None,
                 fares: FareEngine | None = None, emissions: EmissionEngine | None = None) -> None:
        self.graph = graph if graph is not None else self._load_driving_graph(graph_path)
        self._graph_router = WalkingRouter(graph=self.graph) if self.graph is not None else None
        self.fares = fares or fare_engine
        self.emissions = emissions or emission_engine

    @staticmethod
    def _load_driving_graph(graph_path: Path | str | None) -> nx.Graph | None:
        paths = (Path(graph_path),) if graph_path else DRIVING_GRAPH_PATHS
        for path in paths:
            if not path.is_file():
                continue
            try:
                import osmnx as ox

                graph = ox.load_graphml(path)
                LOGGER.info("Loaded Pune driving graph from %s", path)
                return graph
            except Exception as exc:  # Optional local data must not prevent API startup.
                LOGGER.warning("Could not load driving graph %s: %s", path, exc)
        return None

    def _route_points(
        self, start: tuple[float, float], end: tuple[float, float]
    ) -> tuple[list[tuple[float, float]], float]:
        if start == end:
            return [start, end], 0.0
        if self._graph_router is not None:
            try:
                points, meters = self._graph_router._graph_route(start, end)
                return points, meters
            except (nx.NetworkXException, ValueError, KeyError, TypeError) as exc:
                LOGGER.info("Driving graph route unavailable; using offline geometry: %s", exc)
        points = WalkingRouter._fallback_waypoints(start, end)
        # A modest urban-road detour factor avoids pricing the direct geodesic as
        # if autos could travel in a straight line. Geometry remains approximate.
        distance_m = max(polyline_distance_meters(points), haversine_distance_meters(start, end) * 1.22)
        return points, distance_m

    def route(self, request: RouteRequest, night_surcharge: bool | None = None) -> RouteResponse:
        """Return a direct auto trip. ``None`` applies surcharge during Pune night hours."""
        start = (request.origin.lat, request.origin.lng)
        end = (request.destination.lat, request.destination.lng)
        points, distance_meters = self._route_points(start, end)
        distance_km = distance_meters / 1000.0
        breakdown = self.fares.auto(distance_km, night_surcharge=night_surcharge)
        environmental = self.emissions.leg_metrics("auto", distance_km)
        auto_tariff = self.fares.tariffs["auto"]

        leg = RouteLeg(
            mode="auto",
            distance_km=round(distance_km, 3),
            duration_min=round(distance_km / AVERAGE_SPEED_KMH * 60.0, 1),
            fare_inr=breakdown.total_fare,
            geometry=[[round(lat, 7), round(lng, 7)] for lat, lng in points],
            **environmental,
            fare_base_inr=breakdown.base_fare,
            fare_distance_inr=breakdown.distance_fare,
            fare_night_surcharge_inr=breakdown.surcharges,
            fare_rate_per_km=float(auto_tariff["per_km"]),
            night_surcharge_applied=breakdown.surcharges > 0,
            fare_currency=breakdown.currency,
            fare_breakdown=breakdown,
            from_label=request.origin.label,
            to_label=request.destination.label,
        )
        route_environment = self.emissions.route_metrics([leg], leg.distance_km)
        return RouteResponse(
            mode="auto",
            total_distance_km=leg.distance_km,
            total_duration_min=leg.duration_min,
            total_fare_inr=leg.fare_inr,
            legs=[leg],
            fare_breakdown=breakdown,
            **route_environment,
        )

    @staticmethod
    def _as_location_point(point: LocationPoint) -> LocationPoint:
        """Normalize compatible BusStop/MetroStation objects for route models."""
        if isinstance(point, LocationPoint):
            return point
        return LocationPoint(lat=float(point.lat), lng=float(point.lng), label=getattr(point, "name", None))

    def _connector(self, first: LocationPoint, second: LocationPoint) -> RouteLeg | None:
        first = self._as_location_point(first)
        second = self._as_location_point(second)
        walking_request = RouteRequest(origin=first, destination=second)
        walk_meters = walking_router.route(walking_request).total_distance_km * 1000.0
        if walk_meters <= CONNECTOR_WALK_THRESHOLD_METERS:
            return None
        response = self.route(walking_request, night_surcharge=False)
        return response.legs[0]

    def get_first_mile_auto(self, origin: LocationPoint, station: LocationPoint) -> RouteLeg | None:
        """Return an auto leg from origin to station when the gap exceeds 800 m."""
        return self._connector(origin, station)

    def get_last_mile_auto(self, station: LocationPoint, destination: LocationPoint) -> RouteLeg | None:
        """Return an auto leg from station to destination when the gap exceeds 800 m."""
        return self._connector(station, destination)


auto_router = AutoRouter()


def get_first_mile_auto(origin: LocationPoint, station: LocationPoint) -> RouteLeg | None:
    """Module-level helper for bus/metro integrations."""
    return auto_router.get_first_mile_auto(origin, station)


def get_last_mile_auto(station: LocationPoint, destination: LocationPoint) -> RouteLeg | None:
    """Module-level helper for bus/metro integrations."""
    return auto_router.get_last_mile_auto(station, destination)
