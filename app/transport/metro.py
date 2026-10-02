"""Pune Metro path search with walk access and interchange at Civil Court."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx

from app.calculations.distance import haversine_distance_meters, polyline_distance_meters
from app.models.route import LocationPoint, RouteLeg, RouteRequest, RouteResponse
from app.models.transit import MetroLeg, MetroLine, MetroStation
from app.transport.walking import WALKING_SPEED_KMH, WalkingRouter, walking_router

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
NETWORK_PATH = PROJECT_ROOT / "data" / "processed" / "pune_metro_network.json"
ACCESS_RADIUS_METERS = 2500.0
METRO_SPEED_KMH = 38.0
STATION_DWELL_MINUTES = 0.5
INTERCHANGE_PENALTY_MINUTES = 3.0
CO2_GRAMS_PER_PASSENGER_KM = 15.0


class MetroRouter:
    """Find a shortest-time Line 1/Line 2 journey via Civil Court."""

    def __init__(
        self,
        network_path: Path | str = NETWORK_PATH,
        walking: WalkingRouter | None = None,
        access_radius_meters: float = ACCESS_RADIUS_METERS,
    ) -> None:
        self.network_path = Path(network_path)
        self.walking = walking or walking_router
        self.access_radius_meters = access_radius_meters
        self.stations: dict[str, MetroStation] = {}
        self.lines: dict[str, MetroLine] = {}
        self.graph = nx.Graph()
        self._load_network()

    def _load_network(self) -> None:
        try:
            document = json.loads(self.network_path.read_text(encoding="utf-8"))
            self.stations = {row["id"]: MetroStation.model_validate(row) for row in document.get("stations", [])}
            self.lines = {row["line_id"]: MetroLine.model_validate(row) for row in document.get("lines", [])}
            if not self.stations or not self.lines:
                raise ValueError("Metro network has no stations or lines")
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            LOGGER.warning("Metro network could not be loaded from %s: %s", self.network_path, exc)
            self.stations, self.lines = {}, {}
            return

        for line in self.lines.values():
            for station_id in line.route_sequence:
                if station_id not in self.stations:
                    LOGGER.warning("Ignoring metro line %s with missing station %s", line.line_id, station_id)
                    continue
                self.graph.add_node((line.line_id, station_id), station=self.stations[station_id])
            sequence = [station_id for station_id in line.route_sequence if station_id in self.stations]
            for first_id, second_id in zip(sequence, sequence[1:]):
                first, second = self.stations[first_id], self.stations[second_id]
                distance = haversine_distance_meters((first.lat, first.lng), (second.lat, second.lng))
                self.graph.add_edge(
                    (line.line_id, first_id), (line.line_id, second_id),
                    distance_m=distance, transfer=False, line_id=line.line_id,
                )

        # Interchange nodes remain line-specific so the transfer penalty can be
        # counted and rendered as its own journey leg.
        interchange_ids = {"civil-court"}
        for station_id in interchange_ids:
            line_nodes = [(line_id, station_id) for line_id, line in self.lines.items() if station_id in line.route_sequence]
            for first, second in zip(line_nodes, line_nodes[1:]):
                self.graph.add_edge(first, second, distance_m=0.0, transfer=True, station_id=station_id)

    @staticmethod
    def _fare(distance_km: float) -> float:
        if distance_km <= 2:
            return 10.0
        if distance_km <= 6:
            return 20.0
        if distance_km <= 12:
            return 30.0
        return 35.0

    def _nearby_nodes(self, point: LocationPoint) -> list[tuple[float, tuple[str, str]]]:
        point_coords = (point.lat, point.lng)
        candidates = []
        for node, data in self.graph.nodes(data=True):
            station: MetroStation = data["station"]
            distance = haversine_distance_meters(point_coords, (station.lat, station.lng))
            if distance <= self.access_radius_meters:
                candidates.append((distance, node))
        return sorted(candidates, key=lambda item: item[0])

    def _journey_parts(self, path: list[tuple[str, str]]) -> list[dict[str, Any]]:
        if not path:
            return []
        parts: list[dict[str, Any]] = []
        current_line = path[0][0]
        current_stations = [self.stations[path[0][1]]]
        for first, second in zip(path, path[1:]):
            edge = self.graph.edges[first, second]
            if edge.get("transfer"):
                if len(current_stations) > 1:
                    parts.append({"type": "metro", "line_id": current_line, "stations": current_stations})
                transfer_station = self.stations[edge["station_id"]]
                parts.append({"type": "transfer", "station": transfer_station})
                current_line = second[0]
                current_stations = [self.stations[second[1]]]
            else:
                if first[0] != current_line:
                    current_line = first[0]
                    current_stations = [self.stations[first[1]]]
                destination_station = self.stations[second[1]]
                if current_stations[-1].id != destination_station.id:
                    current_stations.append(destination_station)
        if len(current_stations) > 1:
            parts.append({"type": "metro", "line_id": current_line, "stations": current_stations})
        return parts

    @staticmethod
    def _part_distance_km(part: dict[str, Any]) -> float:
        stations: list[MetroStation] = part["stations"]
        return polyline_distance_meters([(station.lat, station.lng) for station in stations]) / 1000.0

    def _select_path(self, request: RouteRequest) -> tuple[list[tuple[str, str]], float, float] | None:
        origin_nodes = self._nearby_nodes(request.origin)
        destination_nodes = self._nearby_nodes(request.destination)
        best: tuple[tuple[float, float, float], list[tuple[str, str]], float, float] | None = None
        for origin_walk_m, origin_node in origin_nodes:
            for destination_walk_m, destination_node in destination_nodes:
                try:
                    path = nx.shortest_path(self.graph, origin_node, destination_node, weight="distance_m")
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
                parts = self._journey_parts(path)
                metro_parts = [part for part in parts if part["type"] == "metro"]
                if not metro_parts:
                    continue
                transit_distance_km = sum(self._part_distance_km(part) for part in metro_parts)
                transit_duration_min = sum(
                    self._part_distance_km(part) / METRO_SPEED_KMH * 60
                    + max(0, len(part["stations"]) - 2) * STATION_DWELL_MINUTES
                    for part in metro_parts
                )
                transfer_count = sum(part["type"] == "transfer" for part in parts)
                total_duration = (
                    transit_duration_min + transfer_count * INTERCHANGE_PENALTY_MINUTES
                    + (origin_walk_m + destination_walk_m) / 1000 / WALKING_SPEED_KMH * 60
                )
                total_distance = transit_distance_km + (origin_walk_m + destination_walk_m) / 1000
                key = (total_duration, total_distance, transit_distance_km)
                if best is None or key < best[0]:
                    best = (key, path, origin_walk_m, destination_walk_m)
        return (best[1], best[2], best[3]) if best else None

    def route(self, request: RouteRequest) -> RouteResponse:
        """Return walking access/egress plus line and interchange legs."""
        selected = self._select_path(request)
        if selected is None:
            if not self.lines:
                raise ValueError("Pune Metro network is not loaded; run scripts/process_metro.py")
            raise ValueError("No metro journey found within 2.5 km of a station")
        path, _, _ = selected
        parts = self._journey_parts(path)
        metro_parts = [part for part in parts if part["type"] == "metro"]
        transit_distance_km = sum(self._part_distance_km(part) for part in metro_parts)
        fare = self._fare(transit_distance_km)

        first_station = self.stations[path[0][1]]
        last_station = self.stations[path[-1][1]]
        walk_to = self.walking.route(RouteRequest(
            origin=request.origin,
            destination=LocationPoint(lat=first_station.lat, lng=first_station.lng, label=first_station.name),
        )).legs[0]
        walk_from = self.walking.route(RouteRequest(
            origin=LocationPoint(lat=last_station.lat, lng=last_station.lng, label=last_station.name),
            destination=request.destination,
        )).legs[0]

        legs: list[RouteLeg] = [RouteLeg(
            mode="walking", distance_km=walk_to.distance_km, duration_min=walk_to.duration_min,
            fare_inr=0.0, co2_grams=0.0, geometry=walk_to.geometry,
        )]
        rail_legs: list[RouteLeg] = []
        for part in parts:
            if part["type"] == "transfer":
                continue
            line: MetroLine = self.lines[part["line_id"]]
            stations: list[MetroStation] = part["stations"]
            distance_km = self._part_distance_km(part)
            duration_min = distance_km / METRO_SPEED_KMH * 60 + max(0, len(stations) - 2) * STATION_DWELL_MINUTES
            rail_legs.append(RouteLeg(
                mode="metro", distance_km=round(distance_km, 3), duration_min=round(duration_min, 1),
                fare_inr=0.0, co2_grams=round(distance_km * CO2_GRAMS_PER_PASSENGER_KM, 1),
                geometry=[[round(station.lat, 7), round(station.lng, 7)] for station in stations],
                line_id=line.line_id, line_name=line.line_name, line_color=line.line_color,
                board_station=stations[0], alight_station=stations[-1],
            ))

        if rail_legs:
            # One through journey fare is charged at boarding and reported once.
            rail_legs[0].fare_inr = fare
        rail_iterator = iter(rail_legs)
        # Reconstruct original transit ordering, keeping each interchange between
        # its two colored rail legs.
        rail_iterator = iter(rail_legs)
        legs = [legs[0]]
        for part in parts:
            if part["type"] == "metro":
                legs.append(next(rail_iterator))
            else:
                station = part["station"]
                legs.append(RouteLeg(
                    mode="transfer", distance_km=0.0, duration_min=INTERCHANGE_PENALTY_MINUTES,
                    fare_inr=0.0, co2_grams=0.0, geometry=[], transfer_station=station,
                ))
        legs.append(RouteLeg(
            mode="walking", distance_km=walk_from.distance_km, duration_min=walk_from.duration_min,
            fare_inr=0.0, co2_grams=0.0, geometry=walk_from.geometry,
        ))
        return RouteResponse(
            mode="metro",
            total_distance_km=round(sum(leg.distance_km for leg in legs), 3),
            total_duration_min=round(sum(leg.duration_min for leg in legs), 1),
            total_fare_inr=fare,
            total_co2_grams=round(sum(leg.co2_grams for leg in legs), 1),
            legs=legs,
        )


metro_router = MetroRouter()
