"""Geodesic distance and waypoint helpers used by routing engines."""

from __future__ import annotations

import math
from collections.abc import Iterable

EARTH_RADIUS_METERS = 6_371_008.8


def haversine_distance_meters(start: tuple[float, float], end: tuple[float, float]) -> float:
    """Return great-circle distance in meters between ``(lat, lng)`` points."""
    lat1, lon1 = map(math.radians, start)
    lat2, lon2 = map(math.radians, end)
    delta_lat = lat2 - lat1
    delta_lon = (lon2 - lon1 + math.pi) % (2 * math.pi) - math.pi
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def haversine_distance_km(start: tuple[float, float], end: tuple[float, float]) -> float:
    """Return great-circle distance in kilometers between ``(lat, lng)`` points."""
    return haversine_distance_meters(start, end) / 1000.0


def destination_point(start: tuple[float, float], bearing_radians: float, distance_meters: float) -> tuple[float, float]:
    """Find a point ``distance_meters`` away from start on a great-circle bearing."""
    lat1, lon1 = map(math.radians, start)
    angular_distance = distance_meters / EARTH_RADIUS_METERS
    sin_lat2 = math.sin(lat1) * math.cos(angular_distance) + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing_radians)
    lat2 = math.asin(max(-1.0, min(1.0, sin_lat2)))
    lon2 = lon1 + math.atan2(
        math.sin(bearing_radians) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    longitude = (math.degrees(lon2) + 540.0) % 360.0 - 180.0
    return math.degrees(lat2), longitude


def interpolate_great_circle(
    start: tuple[float, float], end: tuple[float, float], segments: int = 12
) -> list[tuple[float, float]]:
    """Return endpoints and evenly spaced intermediate points along a bearing."""
    if segments < 1:
        raise ValueError("segments must be at least 1")
    distance = haversine_distance_meters(start, end)
    if distance == 0:
        return [start, end]
    lat1, lon1 = map(math.radians, start)
    lat2, lon2 = map(math.radians, end)
    delta_lon = (lon2 - lon1 + math.pi) % (2 * math.pi) - math.pi
    bearing = math.atan2(
        math.sin(delta_lon) * math.cos(lat2),
        math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon),
    )
    points = [start]
    for index in range(1, segments):
        points.append(destination_point(start, bearing, distance * index / segments))
    points.append(end)
    return points


def polyline_distance_meters(points: Iterable[tuple[float, float]]) -> float:
    """Sum great-circle segment lengths for an iterable of ``(lat, lng)`` points."""
    iterator = iter(points)
    try:
        previous = next(iterator)
    except StopIteration:
        return 0.0
    total = 0.0
    for point in iterator:
        total += haversine_distance_meters(previous, point)
        previous = point
    return total
