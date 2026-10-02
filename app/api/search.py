"""Search and map initialization endpoints for Pune locations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from app.routing.cache import SpatialPointIndex, text_search_cache

router = APIRouter()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = PROJECT_ROOT / "data" / "processed" / "pune_locations.json"
SPATIAL_INDEX_PATH = PROJECT_ROOT / "data" / "processed" / "poi_spatial_index.json"

# Approximate centers are used only to initialize a city/region map before a
# user selects a searched place. They are not administrative boundary claims.
MAJOR_REGIONS: list[dict[str, Any]] = [
    {"name": "Pune", "category": "city", "coordinates": {"lat": 18.5204, "lng": 73.8567}},
    {"name": "Pimpri-Chinchwad", "category": "city", "coordinates": {"lat": 18.6298, "lng": 73.7997}},
    {"name": "Shaniwar Peth", "category": "peth", "coordinates": {"lat": 18.5196, "lng": 73.8553}},
    {"name": "Kothrud", "category": "locality", "coordinates": {"lat": 18.5074, "lng": 73.8077}},
    {"name": "Viman Nagar", "category": "locality", "coordinates": {"lat": 18.5679, "lng": 73.9143}},
    {"name": "Hinjewadi", "category": "locality", "coordinates": {"lat": 18.5913, "lng": 73.7389}},
    {"name": "Hadapsar", "category": "locality", "coordinates": {"lat": 18.5089, "lng": 73.9260}},
    {"name": "Camp", "category": "locality", "coordinates": {"lat": 18.5137, "lng": 73.8790}},
]

_cached_mtime: int | None = None
_cached_locations: list[dict[str, Any]] | None = None
_cached_spatial_mtime: int | None = None
_spatial_index: SpatialPointIndex | None = None


def _load_locations() -> list[dict[str, Any]]:
    """Load index once and reload automatically when the file changes."""
    global _cached_mtime, _cached_locations, _cached_spatial_mtime, _spatial_index
    try:
        modified = INDEX_PATH.stat().st_mtime_ns
    except OSError:
        _cached_mtime = None
        _cached_locations = [
            {
                "id": f"seed_{number:03d}",
                "name": region["name"],
                "category": region["category"],
                "locality": region["name"],
                "coordinates": region["coordinates"],
                "bounding_box": [
                    round(region["coordinates"]["lng"] - 0.001, 7),
                    round(region["coordinates"]["lat"] - 0.001, 7),
                    round(region["coordinates"]["lng"] + 0.001, 7),
                    round(region["coordinates"]["lat"] + 0.001, 7),
                ],
            }
            for number, region in enumerate(MAJOR_REGIONS, start=1)
        ]
        fallback_points = [
            {"id": row["id"], "name": row["name"], "lat": row["coordinates"]["lat"],
             "lng": row["coordinates"]["lng"]}
            for row in _cached_locations
        ]
        _spatial_index = SpatialPointIndex(fallback_points, namespace="poi:seed-locations")
        return _cached_locations

    try:
        spatial_modified = SPATIAL_INDEX_PATH.stat().st_mtime_ns
    except OSError:
        spatial_modified = -1
    if _cached_locations is None or modified != _cached_mtime or spatial_modified != _cached_spatial_mtime:
        try:
            parsed = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            _cached_locations = parsed if isinstance(parsed, list) else []
        except (OSError, json.JSONDecodeError):
            _cached_locations = []
        _cached_mtime = modified
        _cached_spatial_mtime = spatial_modified
        points = []
        for row in _cached_locations:
            coordinates = row.get("coordinates") or {}
            try:
                points.append({
                    "id": str(row.get("id", "")), "name": row.get("name", ""),
                    "lat": float(coordinates["lat"]), "lng": float(coordinates["lng"]),
                })
            except (KeyError, TypeError, ValueError):
                continue
        namespace = f"poi:{modified}:{spatial_modified}"
        _spatial_index = SpatialPointIndex.from_json(SPATIAL_INDEX_PATH, points, namespace=namespace)
    return _cached_locations


def _nearby_locations(lat: float, lng: float, limit: int, radius_meters: float) -> list[dict[str, Any]]:
    locations = _load_locations()
    if _spatial_index is None:
        return []
    by_id = {str(row.get("id", "")): row for row in locations}
    return [
        by_id[str(_spatial_index.records[index].get("id", ""))]
        for _, index in _spatial_index.query_radius(lat, lng, radius_meters)[:limit]
        if str(_spatial_index.records[index].get("id", "")) in by_id
    ]


@router.get("/search")
async def search_locations(
    q: str = Query(default="", description="Place name, locality, or category to search"),
    limit: int = Query(default=10, ge=1, le=100),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    radius_m: float = Query(default=3000, gt=0, le=50000),
) -> list[dict[str, Any]]:
    """Search by text, or return nearby locations when lat/lng are supplied."""
    if lat is not None or lng is not None:
        if lat is None or lng is None:
            return []
        return _nearby_locations(lat, lng, limit, radius_m)
    query = q.strip().casefold()
    if not query:
        return []
    locations = _load_locations()
    cache_key = (_cached_mtime, query, limit)

    def find_matches() -> list[dict[str, Any]]:
        matches: list[tuple[int, dict[str, Any]]] = []
        for location in locations:
            name = str(location.get("name", "")).casefold()
            locality = str(location.get("locality", "")).casefold()
            category = str(location.get("category", "")).casefold()
            if query in name:
                rank = 0 if name.startswith(query) else 1
            elif query in locality:
                rank = 2
            elif query in category:
                rank = 3
            else:
                continue
            matches.append((rank, location))
        matches.sort(key=lambda item: (item[0], str(item[1].get("name", "")).casefold()))
        return [location for _, location in matches[:limit]]

    return text_search_cache.get_or_compute(cache_key, find_matches)


@router.get("/search/nearby")
async def nearby_locations(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_m: float = Query(default=3000, gt=0, le=50000),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Return nearest known Pune places within a radius, using the STRtree."""
    return _nearby_locations(lat, lng, limit, radius_m)


@router.get("/search/reverse")
async def reverse_geocode(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_m: float = Query(default=3000, gt=0, le=50000),
) -> dict[str, Any] | None:
    """Resolve a coordinate to its nearest indexed named place, if close enough."""
    nearby = _nearby_locations(lat, lng, 1, radius_m)
    return nearby[0] if nearby else None


@router.get("/locations")
async def major_locations() -> list[dict[str, Any]]:
    """Return major Pune regions and map centers for initial rendering."""
    return MAJOR_REGIONS
