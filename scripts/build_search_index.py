"""Build a compact, deterministic JSON search index from raw location layers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIRS = (ROOT / "data" / "boundaries", ROOT / "data" / "localities", ROOT / "data" / "pois")
OUTPUT_PATH = ROOT / "data" / "processed" / "pune_locations.json"
LOGGER = logging.getLogger("pune_search_index")


def _read_features(path: Path) -> Iterator[dict[str, Any]]:
    """Yield GeoJSON features and simple JSON location records."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Skipping unreadable location file %s: %s", path, exc)
        return

    if isinstance(document, dict) and document.get("type") == "FeatureCollection":
        yield from (feature for feature in document.get("features", []) if isinstance(feature, dict))
    elif isinstance(document, dict) and document.get("type") == "Feature":
        yield document
    elif isinstance(document, list):
        yield from ({"type": "Feature", "geometry": None, "properties": row} for row in document if isinstance(row, dict))
    elif isinstance(document, dict) and isinstance(document.get("locations"), list):
        yield from ({"type": "Feature", "geometry": None, "properties": row} for row in document["locations"] if isinstance(row, dict))
    else:
        LOGGER.warning("Skipping unsupported JSON format: %s", path)


def _category(properties: dict[str, Any], path: Path) -> str:
    value = properties.get("category") or properties.get("amenity") or properties.get("tourism") or properties.get("shop")
    if value:
        return str(value).strip().lower().replace(" ", "_")
    parent = path.parent.name
    return {"boundaries": "boundary", "localities": "locality", "pois": "poi"}.get(parent, "location")


def _record(feature: dict[str, Any], path: Path) -> dict[str, Any] | None:
    properties = feature.get("properties") or {}
    if not isinstance(properties, dict):
        return None
    name = properties.get("name") or properties.get("name:en") or properties.get("name:mr")
    if not name:
        return None

    geometry_data = feature.get("geometry")
    try:
        geometry = shape(geometry_data) if geometry_data else None
        if geometry is not None and (geometry.is_empty or not geometry.is_valid):
            geometry = geometry.buffer(0) if not geometry.is_empty else None
        if geometry is not None and not geometry.is_empty:
            center = geometry.representative_point()
            min_lng, min_lat, max_lng, max_lat = geometry.bounds
            lat, lng = center.y, center.x
        else:
            coordinates = properties.get("coordinates") or properties.get("center") or {}
            if isinstance(coordinates, dict):
                lat, lng = float(coordinates["lat"]), float(coordinates.get("lng", coordinates.get("lon")))
            elif isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
                lat, lng = float(coordinates[0]), float(coordinates[1])
            else:
                lat = float(properties.get("lat", properties.get("latitude")))
                lng = float(properties.get("lng", properties.get("lon", properties.get("longitude"))))
            min_lng = float(properties.get("min_lng", lng - 0.001))
            min_lat = float(properties.get("min_lat", lat - 0.001))
            max_lng = float(properties.get("max_lng", lng + 0.001))
            max_lat = float(properties.get("max_lat", lat + 0.001))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        LOGGER.warning("Skipping feature %r in %s: missing/invalid geometry or coordinates (%s)", name, path, exc)
        return None

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        LOGGER.warning("Skipping out-of-range coordinates for %s", name)
        return None
    return {
        "name": str(name).strip(),
        "category": _category(properties, path),
        "locality": str(properties.get("locality") or properties.get("addr:suburb") or properties.get("addr:city") or "Pune"),
        "coordinates": {"lat": round(lat, 7), "lng": round(lng, 7)},
        "bounding_box": [round(min_lng, 7), round(min_lat, 7), round(max_lng, 7), round(max_lat, 7)],
    }


def build_index() -> list[dict[str, Any]]:
    records: dict[tuple[str, float, float], dict[str, Any]] = {}
    for input_dir in INPUT_DIRS:
        if not input_dir.exists():
            continue
        for path in sorted(input_dir.rglob("*.json")) + sorted(input_dir.rglob("*.geojson")):
            # A GeoJSON may also match *.json; process each path only once.
            for feature in _read_features(path):
                row = _record(feature, path)
                if row:
                    key = (row["name"].casefold(), row["coordinates"]["lat"], row["coordinates"]["lng"])
                    records.setdefault(key, row)

    ordered = sorted(records.values(), key=lambda row: (row["name"].casefold(), row["category"], row["coordinates"]["lat"], row["coordinates"]["lng"]))
    for number, row in enumerate(ordered, start=1):
        row["id"] = f"loc_{number:03d}"
    # Keep the public schema exact and stable.
    return [
        {key: row[key] for key in ("id", "name", "category", "locality", "coordinates", "bounding_box")}
        for row in ordered
    ]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    index = build_index()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    LOGGER.info("Wrote %d locations to %s", len(index), OUTPUT_PATH)


if __name__ == "__main__":
    main()
