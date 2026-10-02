"""Convert a local PMPML GTFS feed to PuneCentric's compact bus network JSON.

The script accepts a GTFS directory or ZIP. If no usable feed is found, it
writes five clearly labelled approximate PMPML corridor routes so offline
development and the API remain usable. Run from the repository root:

    python scripts/process_gtfs.py
    python scripts/process_gtfs.py path/to/pmpml_gtfs.zip
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import zipfile
import io
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRANSIT_DIR = ROOT / "data" / "transit"
OUTPUT_PATH = ROOT / "data" / "processed" / "pune_bus_network.json"
LOGGER = logging.getLogger("process_gtfs")

# Coordinates are approximate stop-area anchors for demonstration and routing
# development. They should be replaced with verified PMPML/GTFS stop records.
SEED_STOPS: dict[str, dict[str, Any]] = {
    "swargate": {"id": "seed-swargate", "name": "Swargate", "lat": 18.5018, "lng": 73.8636},
    "laxmi_narayan": {"id": "seed-laxmi-narayan", "name": "Laxmi Narayan", "lat": 18.4949, "lng": 73.8614},
    "padmavati": {"id": "seed-padmavati", "name": "Padmavati", "lat": 18.4790, "lng": 73.8620},
    "bharati_vidyapeeth": {"id": "seed-bharati-vidyapeeth", "name": "Bharati Vidyapeeth", "lat": 18.4606, "lng": 73.8574},
    "katraj": {"id": "seed-katraj", "name": "Katraj", "lat": 18.4575, "lng": 73.8675},
    "kothrud_depot": {"id": "seed-kothrud-depot", "name": "Kothrud Depot", "lat": 18.5071, "lng": 73.8072},
    "karve_nagar": {"id": "seed-karve-nagar", "name": "Karve Nagar", "lat": 18.4898, "lng": 73.8190},
    "deccan_gymkhana": {"id": "seed-deccan-gymkhana", "name": "Deccan Gymkhana", "lat": 18.5164, "lng": 73.8400},
    "pmc": {"id": "seed-pmc", "name": "PMC", "lat": 18.5204, "lng": 73.8567},
    "pune_station": {"id": "seed-pune-station", "name": "Pune Station", "lat": 18.5289, "lng": 73.8744},
    "hadapsar": {"id": "seed-hadapsar", "name": "Hadapsar", "lat": 18.5089, "lng": 73.9260},
    "magarpatta": {"id": "seed-magarpatta", "name": "Magarpatta", "lat": 18.5167, "lng": 73.9270},
    "racecourse": {"id": "seed-racecourse", "name": "Racecourse", "lat": 18.4917, "lng": 73.8941},
    "deccan": {"id": "seed-deccan", "name": "Deccan", "lat": 18.5164, "lng": 73.8400},
    "hinjewadi_phase_3": {"id": "seed-hinjewadi-phase-3", "name": "Hinjewadi Phase 3", "lat": 18.5913, "lng": 73.7389},
    "waje": {"id": "seed-waje", "name": "Waje", "lat": 18.5830, "lng": 73.7510},
    "chandani_chowk": {"id": "seed-chandani-chowk", "name": "Chandani Chowk", "lat": 18.5076, "lng": 73.7775},
    "university_circle": {"id": "seed-university-circle", "name": "University Circle", "lat": 18.5362, "lng": 73.8297},
    "shivajinagar": {"id": "seed-shivajinagar", "name": "Shivajinagar", "lat": 18.5308, "lng": 73.8475},
    "viman_nagar": {"id": "seed-viman-nagar", "name": "Viman Nagar", "lat": 18.5679, "lng": 73.9143},
    "yerwada": {"id": "seed-yerwada", "name": "Yerwada", "lat": 18.5471, "lng": 73.8787},
    "bund_garden": {"id": "seed-bund-garden", "name": "Bund Garden", "lat": 18.5362, "lng": 73.8833},
}

SEED_ROUTES: list[dict[str, Any]] = [
    {"route_id": "seed-route-1-out", "route_name": "Route 1 · Swargate ↔ Katraj", "stop_keys": ["swargate", "laxmi_narayan", "padmavati", "bharati_vidyapeeth", "katraj"]},
    {"route_id": "seed-route-1-return", "route_name": "Route 1 · Swargate ↔ Katraj", "stop_keys": ["katraj", "bharati_vidyapeeth", "padmavati", "laxmi_narayan", "swargate"]},
    {"route_id": "seed-route-2-out", "route_name": "Route 2 · Kothrud Depot ↔ Pune Station", "stop_keys": ["kothrud_depot", "karve_nagar", "deccan_gymkhana", "pmc", "pune_station"]},
    {"route_id": "seed-route-2-return", "route_name": "Route 2 · Kothrud Depot ↔ Pune Station", "stop_keys": ["pune_station", "pmc", "deccan_gymkhana", "karve_nagar", "kothrud_depot"]},
    {"route_id": "seed-route-3-out", "route_name": "Route 3 · Hadapsar ↔ Deccan Gymkhana", "stop_keys": ["hadapsar", "magarpatta", "racecourse", "swargate", "deccan"]},
    {"route_id": "seed-route-3-return", "route_name": "Route 3 · Hadapsar ↔ Deccan Gymkhana", "stop_keys": ["deccan", "swargate", "racecourse", "magarpatta", "hadapsar"]},
    {"route_id": "seed-route-4-out", "route_name": "Route 4 · Hinjewadi Phase 3 ↔ PMC", "stop_keys": ["hinjewadi_phase_3", "waje", "chandani_chowk", "university_circle", "shivajinagar", "pmc"]},
    {"route_id": "seed-route-4-return", "route_name": "Route 4 · Hinjewadi Phase 3 ↔ PMC", "stop_keys": ["pmc", "shivajinagar", "university_circle", "chandani_chowk", "waje", "hinjewadi_phase_3"]},
    {"route_id": "seed-route-5-out", "route_name": "Route 5 · Viman Nagar ↔ Swargate", "stop_keys": ["viman_nagar", "yerwada", "bund_garden", "pune_station", "swargate"]},
    {"route_id": "seed-route-5-return", "route_name": "Route 5 · Viman Nagar ↔ Swargate", "stop_keys": ["swargate", "pune_station", "bund_garden", "yerwada", "viman_nagar"]},
]


def _seed_network() -> dict[str, Any]:
    return {
        "source": "seed",
        "approximate": True,
        "notice": "Approximate stop coordinates and corridor sequences for development; not verified PMPML timetable or operational data.",
        "routes": [
            {"route_id": route["route_id"], "route_name": route["route_name"], "stops": [SEED_STOPS[key] for key in route["stop_keys"]]}
            for route in SEED_ROUTES
        ],
    }


def _read_csv(feed: Path, filename: str) -> list[dict[str, str]]:
    """Read a GTFS CSV from a directory or ZIP and release its resources."""
    if feed.is_dir():
        with (feed / filename).open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    with zipfile.ZipFile(feed) as archive:
        candidates = [name for name in archive.namelist() if name.replace("\\", "/").endswith(f"/{filename}") or name == filename]
        if not candidates:
            raise FileNotFoundError(f"{filename} not found in {feed}")
        with archive.open(candidates[0]) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
                return list(csv.DictReader(stream))


def parse_gtfs(feed: Path) -> list[dict[str, Any]]:
    """Parse route patterns from stops, routes, trips, and stop_times GTFS files."""
    stops = {}
    for row in _read_csv(feed, "stops.txt"):
        try:
            stops[row["stop_id"]] = {
                "id": row["stop_id"],
                "name": row.get("stop_name") or row["stop_id"],
                "lat": float(row["stop_lat"]),
                "lng": float(row["stop_lon"]),
            }
        except (KeyError, ValueError):
            continue

    route_rows = {row.get("route_id", ""): row for row in _read_csv(feed, "routes.txt")}
    trips_by_id: dict[str, dict[str, str]] = {}
    for row in _read_csv(feed, "trips.txt"):
        route_id = row.get("route_id", "")
        route_type = route_rows.get(route_id, {}).get("route_type", "3")
        if route_type not in {"3", "700", "701", "702", "703", "704"}:
            continue
        trips_by_id[row.get("trip_id", "")] = row

    stop_times: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(feed, "stop_times.txt"):
        if row.get("trip_id") in trips_by_id:
            stop_times[row["trip_id"]].append(row)

    patterns: dict[tuple[str, str], list[list[str]]] = defaultdict(list)
    for trip_id, trip in trips_by_id.items():
        route_id = trip.get("route_id", "")
        direction = trip.get("direction_id", "0") or "0"
        ordered = sorted(stop_times.get(trip_id, []), key=lambda row: int(row.get("stop_sequence", "0") or 0))
        sequence = [row.get("stop_id", "") for row in ordered if row.get("stop_id") in stops]
        if len(sequence) >= 2:
            patterns[(route_id, direction)].append(sequence)

    result = []
    for (route_id, direction), trips in sorted(patterns.items()):
        # A representative trip with the most stops produces useful geometry
        # while avoiding duplicate service trips in this routing index.
        sequence = max(trips, key=len)
        route_row = route_rows.get(route_id, {})
        route_label = route_row.get("route_short_name") or route_row.get("route_long_name") or route_id
        long_name = route_row.get("route_long_name")
        name = f"{route_label} · {long_name}" if long_name and long_name != route_label else str(route_label)
        result.append({
            "route_id": f"{route_id}-{direction}",
            "route_name": name,
            "stops": [stops[stop_id] for stop_id in sequence],
        })
    return result


def find_feed(explicit_path: str | None) -> Path | None:
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if path.exists():
            return path
        raise FileNotFoundError(f"GTFS feed path does not exist: {path}")
    candidates = [TRANSIT_DIR / "pmpml_gtfs.zip", TRANSIT_DIR / "gtfs.zip", TRANSIT_DIR / "pmpml_gtfs"]
    return next((path for path in candidates if path.exists()), None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gtfs", nargs="?", help="GTFS directory or ZIP file (defaults to data/transit/pmpml_gtfs.zip)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    feed = find_feed(args.gtfs)
    routes = []
    source = "seed"
    if feed:
        try:
            routes = parse_gtfs(feed)
            if routes:
                source = f"GTFS: {feed.name}"
                LOGGER.info("Parsed %d bus route patterns from %s", len(routes), feed)
            else:
                LOGGER.warning("No usable bus route patterns found in %s; using seed network", feed)
        except Exception as exc:
            LOGGER.warning("Could not parse GTFS feed %s (%s); using seed network", feed, exc)
    else:
        LOGGER.info("No local PMPML GTFS feed found; using offline corridor seed")

    document = _seed_network() if not routes else {
        "source": source,
        "approximate": False,
        "notice": "Parsed GTFS stop and trip pattern data. Timetables, service calendars, and live arrivals are not modeled.",
        "routes": routes,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Wrote %d bus routes to %s", len(document["routes"]), OUTPUT_PATH)


if __name__ == "__main__":
    main()
