"""Small thread-safe TTL/LRU caches and reusable projected point indexes."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import threading
import time
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

from app.calculations.distance import haversine_distance_meters

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


class TTLRUCache(Generic[T]):
    """Bounded LRU cache that expires entries after a configurable TTL."""

    def __init__(self, maxsize: int = 512, ttl_seconds: float = 120.0) -> None:
        self.maxsize = max(1, int(maxsize))
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._entries: OrderedDict[Any, tuple[float, T]] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: Any, default: Any = None) -> T | Any:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return default
            expires_at, value = entry
            if expires_at <= now:
                del self._entries[key]
                return default
            self._entries.move_to_end(key)
            return copy.deepcopy(value)

    def set(self, key: Any, value: T) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic() + self.ttl_seconds, copy.deepcopy(value))
            self._entries.move_to_end(key)
            while len(self._entries) > self.maxsize:
                self._entries.popitem(last=False)

    def get_or_compute(self, key: Any, compute: Callable[[], T]) -> T:
        cached = self.get(key, _MISSING)
        if cached is not _MISSING:
            return cached
        value = compute()
        self.set(key, value)
        return copy.deepcopy(value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_MISSING = object()
route_response_cache: TTLRUCache[Any] = TTLRUCache(maxsize=256, ttl_seconds=120)
spatial_query_cache: TTLRUCache[list[int]] = TTLRUCache(maxsize=8192, ttl_seconds=300)
text_search_cache: TTLRUCache[list[dict[str, Any]]] = TTLRUCache(maxsize=2048, ttl_seconds=60)


def _coordinates(point: Any) -> tuple[float, float]:
    if hasattr(point, "lat") and hasattr(point, "lng"):
        return round(float(point.lat), 4), round(float(point.lng), 4)
    if isinstance(point, dict):
        if "coordinates" in point and isinstance(point["coordinates"], dict):
            point = point["coordinates"]
        return round(float(point["lat"]), 4), round(float(point.get("lng", point.get("lon"))), 4)
    return round(float(point[0]), 4), round(float(point[1]), 4)


def route_cache_key(namespace: str, origin: Any, destination: Any, options: Any = None) -> tuple[Any, ...]:
    """Build a stable cache key from rounded coordinates and normalized options."""
    if hasattr(options, "model_dump"):
        options = options.model_dump(mode="json", exclude_none=True)
    stable_options = json.dumps(options or {}, sort_keys=True, separators=(",", ":"), default=str)
    return namespace, _coordinates(origin), _coordinates(destination), stable_options


@lru_cache(maxsize=1)
def _projector() -> Any:
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


def _utm_coordinates(lat: float, lng: float) -> tuple[float, float]:
    """Project WGS84 coordinates to UTM zone 43N (Pune) in meters."""
    try:
        return tuple(_projector().transform(lng, lat))  # type: ignore[return-value]
    except Exception:
        # Approximate equirectangular fallback near Pune for environments without pyproj.
        reference_lat = math.radians(18.52)
        return (lng - 73.8567) * 111_320 * math.cos(reference_lat), (lat - 18.52) * 110_574


class SpatialPointIndex:
    """STRtree-backed point lookup, with a distance-scan fallback."""

    def __init__(self, records: list[dict[str, Any]], *, namespace: str = "points") -> None:
        self.records = records
        fingerprint_source = [
            (str(row.get("id", "")), round(float(row["lat"]), 7), round(float(row["lng"]), 7))
            for row in records
        ]
        fingerprint = hashlib.sha1(json.dumps(fingerprint_source, separators=(",", ":")).encode()).hexdigest()[:12]
        self.namespace = f"{namespace}:{fingerprint}"
        self._xy: list[tuple[float, float]] = []
        self._tree = None
        self._points: list[Any] = []
        self._geometry_ids: dict[int, int] = {}
        try:
            from shapely.geometry import Point
            from shapely.strtree import STRtree

            for record in records:
                lat, lng = float(record["lat"]), float(record["lng"])
                x = float(record["x"]) if record.get("x") is not None else None
                y = float(record["y"]) if record.get("y") is not None else None
                if x is None or y is None:
                    x, y = _utm_coordinates(lat, lng)
                self._xy.append((x, y))
                self._points.append(Point(x, y))
            if self._points:
                self._tree = STRtree(self._points)
                self._geometry_ids = {id(point): index for index, point in enumerate(self._points)}
        except (ImportError, ValueError, TypeError) as exc:
            LOGGER.debug("STRtree unavailable for %s; using coordinate scan: %s", namespace, exc)
            self._tree = None
            self._points = []

    @classmethod
    def from_json(cls, path: Path | str, fallback_records: list[dict[str, Any]], *, namespace: str) -> "SpatialPointIndex":
        """Load projected index records when compatible; otherwise index source data."""
        file_path = Path(path)
        try:
            document = json.loads(file_path.read_text(encoding="utf-8"))
            records = document.get("records", []) if isinstance(document, dict) else []
            source_ids = {str(row.get("id")) for row in fallback_records}
            index_ids = {str(row.get("id")) for row in records}
            source_coords = {
                str(row.get("id")): (round(float(row["lat"]), 7), round(float(row["lng"]), 7))
                for row in fallback_records
            }
            index_coords = {
                str(row.get("id")): (round(float(row["lat"]), 7), round(float(row["lng"]), 7))
                for row in records
            }
            if records and source_ids == index_ids and source_coords == index_coords:
                return cls(records, namespace=namespace)
        except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            LOGGER.debug("Spatial index %s unavailable; rebuilding in memory: %s", file_path, exc)
        return cls(fallback_records, namespace=namespace)

    def _tree_candidates(self, lat: float, lng: float, radius_meters: float) -> list[int]:
        if self._tree is None:
            return list(range(len(self.records)))
        try:
            from shapely.geometry import Point

            x, y = _utm_coordinates(lat, lng)
            geometries = self._tree.query(Point(x, y).buffer(radius_meters))
            results = []
            for geometry in geometries:
                # Shapely 2 returns integer indices; support geometry results too.
                if isinstance(geometry, (int,)) or getattr(geometry, "dtype", None) is not None:
                    try:
                        results.extend(int(value) for value in geometry)
                    except TypeError:
                        results.append(int(geometry))
                else:
                    index = self._geometry_ids.get(id(geometry))
                    if index is not None:
                        results.append(index)
            return list(dict.fromkeys(results))
        except (ImportError, ValueError, TypeError, AttributeError) as exc:
            LOGGER.debug("STRtree query failed for %s; scanning records: %s", self.namespace, exc)
            return list(range(len(self.records)))

    def query_radius(self, lat: float, lng: float, radius_meters: float) -> list[tuple[float, int]]:
        """Return exact-distance sorted (meters, record index) rows within radius."""
        qlat, qlng = round(float(lat), 4), round(float(lng), 4)
        radius = max(0.0, float(radius_meters))
        key = (self.namespace, qlat, qlng, round(radius, 1))
        # The cache query is padded to preserve correctness near the 4-decimal
        # quantization boundary; distances are always recomputed at the exact point.
        possible = spatial_query_cache.get_or_compute(
            key,
            lambda: self._tree_candidates(qlat, qlng, radius + 20.0),
        )
        matches = []
        for index in possible:
            row = self.records[index]
            distance = haversine_distance_meters((lat, lng), (float(row["lat"]), float(row["lng"])))
            if distance <= radius:
                matches.append((distance, index))
        matches.sort(key=lambda item: (item[0], str(self.records[item[1]].get("id", ""))))
        return matches


def nearest_with_cache(namespace: str, lat: float, lng: float, radius_meters: float, compute: Callable[[], list[int]]) -> list[int]:
    """Cache candidate record indices for a quantized coordinate and radius."""
    key = (namespace, round(lat, 4), round(lng, 4), round(float(radius_meters), 1))
    return spatial_query_cache.get_or_compute(key, compute)
