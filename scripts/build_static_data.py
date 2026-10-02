"""Validate and stage Pune's normalized datasets as deployable static JSON.

The script is safe to run repeatedly and writes compact UTF-8 files to
``public/data``. Vercel serves these files from its static delivery layer.
Run directly before deployment or through the Vercel build hook in ``pyproject.toml``:

    python scripts/build_static_data.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
DEFAULT_OUTPUT_DIR = ROOT / "public" / "data"
LOGGER = logging.getLogger("build_static_data")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant {value}")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Could not read valid JSON dataset {path}: {exc}") from exc


def _validate_coordinates(lat: Any, lng: Any, context: str) -> None:
    try:
        latitude, longitude = float(lat), float(lng)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Missing numeric coordinates in {context}") from exc
    if not (math.isfinite(latitude) and math.isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError(f"Out-of-range coordinates in {context}: {latitude}, {longitude}")


def _validate_locations(document: Any) -> int:
    if not isinstance(document, list) or not document:
        raise ValueError("pune_locations.json must contain a non-empty JSON array")
    for index, row in enumerate(document):
        if not isinstance(row, dict) or not all(key in row for key in ("id", "name", "category", "locality", "coordinates", "bounding_box")):
            raise ValueError(f"Invalid location record at index {index}")
        coords = row["coordinates"]
        if not isinstance(coords, dict):
            raise ValueError(f"Invalid coordinates for location {row.get('id')}")
        _validate_coordinates(coords.get("lat"), coords.get("lng"), f"location {row.get('id')}")
        box = row["bounding_box"]
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError(f"Invalid bounding_box for location {row.get('id')}")
    return len(document)


def _validate_bus(document: Any) -> int:
    routes = document.get("routes") if isinstance(document, dict) else None
    if not isinstance(routes, list) or not routes:
        raise ValueError("pune_bus_network.json must contain at least one route")
    stop_count = 0
    for route in routes:
        stops = route.get("stops") if isinstance(route, dict) else None
        if not isinstance(stops, list) or len(stops) < 2:
            raise ValueError(f"Bus route {route.get('route_id', '?') if isinstance(route, dict) else '?'} has fewer than two stops")
        for stop in stops:
            if not isinstance(stop, dict) or not stop.get("id") or not stop.get("name"):
                raise ValueError("Bus stops must include an id and name")
            _validate_coordinates(stop.get("lat"), stop.get("lng"), f"bus stop {stop['id']}")
            stop_count += 1
    return stop_count


def _validate_metro(document: Any) -> int:
    stations = document.get("stations") if isinstance(document, dict) else None
    lines = document.get("lines") if isinstance(document, dict) else None
    if not isinstance(stations, list) or not stations or not isinstance(lines, list) or not lines:
        raise ValueError("pune_metro_network.json must contain stations and lines")
    station_ids = set()
    for station in stations:
        if not isinstance(station, dict) or not station.get("id") or not station.get("name"):
            raise ValueError("Metro stations must include an id and name")
        station_ids.add(str(station["id"]))
        _validate_coordinates(station.get("lat"), station.get("lng"), f"metro station {station['id']}")
    for line in lines:
        sequence = line.get("route_sequence") if isinstance(line, dict) else None
        if not isinstance(sequence, list) or len(sequence) < 2:
            raise ValueError("Every metro line must define a route_sequence with at least two stations")
        missing = set(map(str, sequence)) - station_ids
        if missing:
            raise ValueError(f"Metro line {line.get('line_id', '?')} references unknown stations: {sorted(missing)}")
    return len(stations)


DATASETS: tuple[tuple[str, Callable[[Any], int]], ...] = (
    ("pune_locations.json", _validate_locations),
    ("pune_bus_network.json", _validate_bus),
    ("pune_metro_network.json", _validate_metro),
)


def _atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(contents, encoding="utf-8", newline="\n")
    temporary.replace(path)


def build_static_data(output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Validate source datasets, write compact copies, and produce a manifest."""
    destination = Path(output_dir).expanduser().resolve()
    manifest: dict[str, Any] = {"schema_version": 1, "datasets": {}}

    for filename, validator in DATASETS:
        source = PROCESSED_DIR / filename
        document = _read_json(source)
        item_count = validator(document)
        serialized = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        payload = serialized.encode("utf-8")
        target = destination / filename
        _atomic_write(target, serialized)
        manifest["datasets"][filename] = {
            "records": item_count,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        LOGGER.info("Packaged %s (%d records, %d bytes)", filename, item_count, len(payload))

    manifest_path = destination / "static_data_manifest.json"
    _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    LOGGER.info("Wrote manifest to %s", manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Staging directory (defaults to public/data)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_static_data(args.output_dir)


if __name__ == "__main__":
    main()
