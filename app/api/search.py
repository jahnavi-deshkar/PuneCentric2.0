"""Search and map initialization endpoints for Pune locations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = PROJECT_ROOT / "data" / "processed" / "pune_locations.json"

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


def _load_locations() -> list[dict[str, Any]]:
    """Load index once and reload automatically when the file changes."""
    global _cached_mtime, _cached_locations
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
        return _cached_locations

    if _cached_locations is None or modified != _cached_mtime:
        try:
            parsed = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            _cached_locations = parsed if isinstance(parsed, list) else []
        except (OSError, json.JSONDecodeError):
            _cached_locations = []
        _cached_mtime = modified
    return _cached_locations


@router.get("/search")
async def search_locations(
    q: str = Query(default="", description="Place name, locality, or category to search"),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Return locations matching name, locality, or category."""
    query = q.strip().casefold()
    if not query:
        return []

    matches: list[tuple[int, dict[str, Any]]] = []
    for location in _load_locations():
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


@router.get("/locations")
async def major_locations() -> list[dict[str, Any]]:
    """Return major Pune regions and map centers for initial rendering."""
    return MAJOR_REGIONS
