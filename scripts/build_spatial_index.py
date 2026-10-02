"""Pre-project Pune POIs, bus stops, and metro stations for STRtree lookup.

Writes portable JSON index records. Runtime routers build a Shapely STRtree
once from these projected points, avoiding repeated coordinate projection and
linear nearest-neighbor scans. Run after the location and transit processors:

    python scripts/build_search_index.py
    python scripts/process_gtfs.py
    python scripts/process_metro.py
    python scripts/build_spatial_index.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RAW_LOCATION_DIRS = (ROOT / "data" / "boundaries", ROOT / "data" / "localities", ROOT / "data" / "pois")
LOGGER = logging.getLogger("build_spatial_index")
PROJECT = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


def _valid_record(record: dict[str, Any]) -> dict[str, Any] | None:
    try:
        lat = float(record["lat"])
        lng = float(record.get("lng", record.get("lon")))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None
        x, y = PROJECT.transform(lng, lat)
        return {**record, "lat": lat, "lng": lng, "x": round(x, 3), "y": round(y, 3)}
    except (KeyError, TypeError, ValueError):
        return None


def _load_locations() -> list[dict[str, Any]]:
    path = PROCESSED / "pune_locations.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.info("Processed search index unavailable (%s); reading raw GeoJSON layers", exc)
        return _load_raw_location_layers()
    records = []
    for row in rows if isinstance(rows, list) else []:
        coords = row.get("coordinates") or {}
        record = _valid_record({
            "id": str(row.get("id", "")), "name": row.get("name", ""),
            "category": row.get("category", "location"), "locality": row.get("locality", "Pune"),
            "lat": coords.get("lat"), "lng": coords.get("lng"),
        })
        if record:
            records.append(record)
    return records or _load_raw_location_layers()


def _load_raw_location_layers() -> list[dict[str, Any]]:
    """Read GeoJSON features directly when the normalized search file is absent."""
    records: dict[tuple[str, float, float], dict[str, Any]] = {}
    for directory in RAW_LOCATION_DIRS:
        if not directory.exists():
            continue
        paths = sorted(set(directory.rglob("*.json")) | set(directory.rglob("*.geojson")))
        for path in paths:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(document, dict) and document.get("type") == "FeatureCollection":
                features = document.get("features", [])
            elif isinstance(document, dict) and document.get("type") == "Feature":
                features = [document]
            else:
                features = [{"properties": item} for item in document] if isinstance(document, list) else []
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                properties = feature.get("properties") or {}
                if not isinstance(properties, dict):
                    continue
                name = properties.get("name") or properties.get("name:en")
                if not name:
                    continue
                try:
                    geometry = shape(feature["geometry"]) if feature.get("geometry") else None
                    if geometry is not None and not geometry.is_empty:
                        center = geometry.representative_point()
                        lat, lng = center.y, center.x
                    else:
                        coords = properties.get("coordinates") or properties.get("center") or {}
                        if isinstance(coords, dict):
                            lat = float(coords["lat"])
                            lng = float(coords.get("lng", coords.get("lon")))
                        else:
                            lat = float(properties.get("lat", properties.get("latitude")))
                            lng = float(properties.get("lng", properties.get("lon", properties.get("longitude"))))
                    category = str(properties.get("category") or properties.get("amenity") or {
                        "boundaries": "boundary", "localities": "locality", "pois": "poi"
                    }.get(directory.name, "location"))
                    key = (str(name).casefold(), round(lat, 7), round(lng, 7))
                    record = _valid_record({
                        "id": str(properties.get("id") or feature.get("id") or f"raw-{len(records) + 1}"),
                        "name": str(name), "category": category,
                        "locality": str(properties.get("locality") or properties.get("addr:suburb") or "Pune"),
                        "lat": lat, "lng": lng,
                    })
                    if record:
                        records.setdefault(key, record)
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue
    return list(records.values())


def _load_bus_stops() -> list[dict[str, Any]]:
    path = PROCESSED / "pune_bus_network.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Bus network unavailable (%s); bus spatial index will be empty", exc)
        return []
    unique: dict[str, dict[str, Any]] = {}
    for route in document.get("routes", []) if isinstance(document, dict) else []:
        for stop in route.get("stops", []):
            record = _valid_record({
                "id": str(stop.get("id", "")), "name": stop.get("name", "Bus stop"),
                "lat": stop.get("lat"), "lng": stop.get("lng"),
            })
            if record and record["id"]:
                unique.setdefault(record["id"], record)
    return sorted(unique.values(), key=lambda row: row["id"])


def _load_metro_stations() -> list[dict[str, Any]]:
    path = PROCESSED / "pune_metro_network.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Metro network unavailable (%s); metro spatial index will be empty", exc)
        return []
    records = []
    for station in document.get("stations", []) if isinstance(document, dict) else []:
        record = _valid_record({
            "id": str(station.get("id", "")), "name": station.get("name", "Metro station"),
            "lat": station.get("lat"), "lng": station.get("lng"),
        })
        if record and record["id"]:
            records.append(record)
    return records


def write_index(name: str, records: list[dict[str, Any]]) -> Path:
    """Validate the projected points with STRtree and write a portable index."""
    geometries = [Point(row["x"], row["y"]) for row in records]
    if geometries:
        STRtree(geometries)  # validates that the input is accepted by Shapely's index.
    document = {
        "schema_version": 1,
        "index_type": "shapely.STRtree",
        "crs": "EPSG:32643",
        "source_crs": "EPSG:4326",
        "record_count": len(records),
        "records": records,
    }
    output = PROCESSED / name
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    LOGGER.info("Wrote %d indexed points to %s", len(records), output)
    return output


def build_indexes() -> dict[str, Path]:
    return {
        "poi": write_index("poi_spatial_index.json", _load_locations()),
        "bus": write_index("bus_spatial_index.json", _load_bus_stops()),
        "metro": write_index("metro_spatial_index.json", _load_metro_stations()),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_indexes()


if __name__ == "__main__":
    main()
