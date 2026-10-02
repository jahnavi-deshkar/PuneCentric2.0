"""Pedestrian routing with optional OSMnx graph routing and offline fallback."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import networkx as nx
from shapely.geometry import LineString

from app.calculations.fares import fare_engine
from app.calculations.emissions import emission_engine
from app.calculations.distance import (
    destination_point,
    haversine_distance_meters,
    interpolate_great_circle,
    polyline_distance_meters,
)
from app.models.route import RouteLeg, RouteRequest, RouteResponse

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_PATHS = (
    PROJECT_ROOT / "data" / "processed" / "pune_walk.graphml",
    PROJECT_ROOT / "data" / "processed" / "walking_graph.graphml",
)
WALKING_SPEED_KMH = 4.5


class WalkingRouter:
    """Calculate walking routes. Pass an OSMnx pedestrian graph to enable routing."""

    def __init__(self, graph: nx.Graph | None = None, graph_path: Path | str | None = None) -> None:
        self.graph = graph if graph is not None else self._load_graph(graph_path)

    @staticmethod
    def _load_graph(graph_path: Path | str | None) -> nx.Graph | None:
        paths = (Path(graph_path),) if graph_path else DEFAULT_GRAPH_PATHS
        for path in paths:
            if not path.is_file():
                continue
            try:
                import osmnx as ox

                graph = ox.load_graphml(path)
                LOGGER.info("Loaded pedestrian graph from %s", path)
                return graph
            except Exception as exc:  # An unavailable/invalid optional graph should not break API startup.
                LOGGER.warning("Could not load pedestrian graph %s: %s", path, exc)
        return None

    @staticmethod
    def _fallback_waypoints(start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
        """Build a deterministic, slightly winding line for offline map display."""
        direct_distance = haversine_distance_meters(start, end)
        segments = max(2, min(24, math.ceil(direct_distance / 250.0)))
        points = interpolate_great_circle(start, end, segments)
        if direct_distance < 20:
            return points

        delta_lon = math.radians(end[1] - start[1])
        lat1, lat2 = math.radians(start[0]), math.radians(end[0])
        bearing = math.atan2(
            math.sin(delta_lon) * math.cos(lat2),
            math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon),
        )
        perpendicular_bearing = bearing + math.pi / 2
        jitter_m = min(35.0, max(8.0, direct_distance * 0.035))
        routed = [points[0]]
        for index, point in enumerate(points[1:-1], start=1):
            progress = index / segments
            offset = jitter_m * math.sin(progress * 3 * math.pi) * math.sin(progress * math.pi)
            routed.append(destination_point(point, perpendicular_bearing if offset >= 0 else perpendicular_bearing + math.pi, abs(offset)))
        routed.append(points[-1])
        return routed

    @staticmethod
    def _nearest_node(graph: nx.Graph, point: tuple[float, float]) -> Any:
        """Find the nearest graph node, projecting coordinates when graph CRS is projected."""
        graph_crs = graph.graph.get("crs", "EPSG:4326")
        x, y = point[1], point[0]
        is_projected = False
        try:
            from pyproj import CRS, Transformer

            crs = CRS.from_user_input(graph_crs)
            if not crs.is_geographic:
                is_projected = True
                transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
                x, y = transformer.transform(x, y)
        except Exception as exc:
            LOGGER.debug("Graph CRS unavailable; assuming WGS84 node coordinates: %s", exc)

        nearest_node = None
        nearest_distance = math.inf
        for node, data in graph.nodes(data=True):
            if "x" not in data or "y" not in data:
                continue
            if is_projected:
                distance = math.hypot(float(data["x"]) - x, float(data["y"]) - y)
            else:
                distance = haversine_distance_meters(point, (float(data["y"]), float(data["x"])))
            if distance < nearest_distance:
                nearest_node, nearest_distance = node, distance
        if nearest_node is None:
            raise ValueError("Pedestrian graph has no nodes with x/y coordinates")
        return nearest_node

    @staticmethod
    def _coordinates_to_latlng(graph: nx.Graph, x: float, y: float) -> tuple[float, float]:
        """Convert graph coordinates into response ``(lat, lng)`` coordinates."""
        graph_crs = graph.graph.get("crs", "EPSG:4326")
        try:
            from pyproj import CRS, Transformer

            crs = CRS.from_user_input(graph_crs)
            if not crs.is_geographic:
                transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
                longitude, latitude = transformer.transform(x, y)
                return float(latitude), float(longitude)
        except Exception as exc:
            LOGGER.debug("Could not transform graph coordinates; assuming WGS84: %s", exc)
        return float(y), float(x)

    @staticmethod
    def _edge_data(graph: nx.Graph, start: Any, end: Any) -> dict[str, Any]:
        data = graph.get_edge_data(start, end)
        if data is None:
            return {}
        if graph.is_multigraph():
            return min(data.values(), key=lambda edge: float(edge.get("length", math.inf)))
        return data

    @staticmethod
    def _append_point(points: list[tuple[float, float]], point: tuple[float, float]) -> None:
        if not points or haversine_distance_meters(points[-1], point) > 0.2:
            points.append(point)

    def _graph_route(
        self, start: tuple[float, float], end: tuple[float, float]
    ) -> tuple[list[tuple[float, float]], float]:
        if self.graph is None or self.graph.number_of_nodes() == 0:
            raise ValueError("No pedestrian graph is loaded")
        start_node = self._nearest_node(self.graph, start)
        end_node = self._nearest_node(self.graph, end)
        try:
            nodes = nx.shortest_path(self.graph, start_node, end_node, weight="length")
            graph = self.graph
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            undirected = self.graph.to_undirected(as_view=True)
            nodes = nx.shortest_path(undirected, start_node, end_node, weight="length")
            graph = undirected

        path = [start]
        start_data = self.graph.nodes[start_node]
        start_xy = self._coordinates_to_latlng(self.graph, float(start_data["x"]), float(start_data["y"]))
        self._append_point(path, start_xy)
        network_length = 0.0
        for first, second in zip(nodes, nodes[1:]):
            edge = self._edge_data(graph, first, second)
            edge_length = float(edge.get("length", haversine_distance_meters(
                self._coordinates_to_latlng(self.graph, float(self.graph.nodes[first]["x"]), float(self.graph.nodes[first]["y"])),
                self._coordinates_to_latlng(self.graph, float(self.graph.nodes[second]["x"]), float(self.graph.nodes[second]["y"])),
            )))
            network_length += edge_length
            geometry = edge.get("geometry")
            if geometry is not None:
                coordinates = list(geometry.coords) if isinstance(geometry, LineString) else []
                if coordinates:
                    first_xy = self._coordinates_to_latlng(self.graph, float(self.graph.nodes[first]["x"]), float(self.graph.nodes[first]["y"]))
                    latlng_coordinates = [self._coordinates_to_latlng(self.graph, float(x), float(y)) for x, y, *_ in coordinates]
                    if haversine_distance_meters(first_xy, latlng_coordinates[0]) > haversine_distance_meters(first_xy, latlng_coordinates[-1]):
                        latlng_coordinates.reverse()
                    for point in latlng_coordinates:
                        self._append_point(path, point)
            second_data = self.graph.nodes[second]
            self._append_point(path, self._coordinates_to_latlng(self.graph, float(second_data["x"]), float(second_data["y"])))

        end_data = self.graph.nodes[end_node]
        end_xy = self._coordinates_to_latlng(self.graph, float(end_data["x"]), float(end_data["y"]))
        self._append_point(path, end)
        total_meters = haversine_distance_meters(start, start_xy) + network_length + haversine_distance_meters(end_xy, end)
        return path, total_meters

    def route(self, request: RouteRequest) -> RouteResponse:
        """Return a walking route, using the graph when available and fallback otherwise."""
        start = (request.origin.lat, request.origin.lng)
        end = (request.destination.lat, request.destination.lng)
        try:
            if start == end:
                coordinates, distance_meters = [start, end], 0.0
            elif self.graph is not None:
                coordinates, distance_meters = self._graph_route(start, end)
            else:
                coordinates = self._fallback_waypoints(start, end)
                distance_meters = polyline_distance_meters(coordinates)
        except (nx.NetworkXException, ValueError, KeyError, TypeError) as exc:
            LOGGER.info("Walking graph route unavailable; using offline fallback: %s", exc)
            coordinates = [start, end] if start == end else self._fallback_waypoints(start, end)
            distance_meters = polyline_distance_meters(coordinates)

        distance_km = distance_meters / 1000.0
        duration_min = distance_km / WALKING_SPEED_KMH * 60.0
        geometry = [[round(lat, 7), round(lng, 7)] for lat, lng in coordinates]
        environmental = emission_engine.leg_metrics("walking", distance_km)
        leg = RouteLeg(
            mode="walking",
            distance_km=round(distance_km, 3),
            duration_min=round(duration_min, 1),
            fare_inr=0.0,
            co2_grams=float(environmental["co2_grams"]),
            geometry=geometry,
            fare_breakdown=fare_engine.walking(),
            co2_saved_grams=float(environmental["co2_saved_grams"]),
            eco_badge=str(environmental["eco_badge"]),
            trees_equivalent=float(environmental["trees_equivalent"]),
            smartphone_charges_equivalent=float(environmental["smartphone_charges_equivalent"]),
            private_car_baseline_co2_grams=float(environmental["private_car_baseline_co2_grams"]),
        )
        route_environment = emission_engine.route_metrics([leg], leg.distance_km)
        return RouteResponse(
            mode="walking",
            total_distance_km=leg.distance_km,
            total_duration_min=leg.duration_min,
            total_fare_inr=0.0,
            total_co2_grams=float(route_environment["total_co2_grams"]),
            co2_grams=float(route_environment["co2_grams"]),
            legs=[leg],
            fare_breakdown=fare_engine.combine([leg.fare_breakdown], mode="walking"),
            co2_saved_grams=float(route_environment["co2_saved_grams"]),
            eco_badge=str(route_environment["eco_badge"]),
            trees_equivalent=float(route_environment["trees_equivalent"]),
            smartphone_charges_equivalent=float(route_environment["smartphone_charges_equivalent"]),
            private_car_baseline_co2_grams=float(route_environment["private_car_baseline_co2_grams"]),
        )


walking_router = WalkingRouter()
