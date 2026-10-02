"""Write Pune Metro's Line 1 and Line 2 station network as JSON.

The station order follows Pune Metro's published corridor lists. Coordinates
are curated station-area map anchors based on public mapping and are rounded to
five decimals. They are approximate platform locations, not survey-grade
coordinates; verify them against official survey data before precise routing.

    python scripts/process_metro.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "processed" / "pune_metro_network.json"
LOGGER = logging.getLogger("process_metro")

STATIONS: dict[str, dict[str, Any]] = {
    "pcmc": {"id": "pcmc", "name": "PCMC", "lat": 18.62980, "lng": 73.79970},
    "sant-tukaram-nagar": {"id": "sant-tukaram-nagar", "name": "Sant Tukaram Nagar", "lat": 18.61820, "lng": 73.81320},
    "bhosari": {"id": "bhosari", "name": "Bhosari", "lat": 18.60900, "lng": 73.82160},
    "kasarwadi": {"id": "kasarwadi", "name": "Kasarwadi", "lat": 18.60160, "lng": 73.81950},
    "phugewadi": {"id": "phugewadi", "name": "Phugewadi", "lat": 18.59090, "lng": 73.82480},
    "dapodi": {"id": "dapodi", "name": "Dapodi", "lat": 18.58040, "lng": 73.83040},
    "bopodi": {"id": "bopodi", "name": "Bopodi", "lat": 18.57270, "lng": 73.83150},
    "khadki": {"id": "khadki", "name": "Khadki", "lat": 18.56190, "lng": 73.83270},
    "range-hill": {"id": "range-hill", "name": "Range Hill", "lat": 18.54870, "lng": 73.83270},
    "shivajinagar": {"id": "shivajinagar", "name": "Shivajinagar", "lat": 18.53080, "lng": 73.84750},
    "civil-court": {"id": "civil-court", "name": "Civil Court", "lat": 18.52709, "lng": 73.85741},
    "budhwar-peth": {"id": "budhwar-peth", "name": "Budhwar Peth", "lat": 18.51820, "lng": 73.85670},
    "mandai": {"id": "mandai", "name": "Mandai", "lat": 18.51020, "lng": 73.85600},
    "swargate": {"id": "swargate", "name": "Swargate", "lat": 18.50180, "lng": 73.86360},
    "vanaz": {"id": "vanaz", "name": "Vanaz", "lat": 18.50710, "lng": 73.80527},
    "anand-nagar": {"id": "anand-nagar", "name": "Anand Nagar", "lat": 18.50060, "lng": 73.81440},
    "ideal-colony": {"id": "ideal-colony", "name": "Ideal Colony", "lat": 18.50730, "lng": 73.82240},
    "nal-stop": {"id": "nal-stop", "name": "Nal Stop", "lat": 18.50960, "lng": 73.83160},
    "garware-college": {"id": "garware-college", "name": "Garware College", "lat": 18.51550, "lng": 73.83710},
    "deccan-gymkhana": {"id": "deccan-gymkhana", "name": "Deccan Gymkhana", "lat": 18.51640, "lng": 73.84000},
    "sambhaji-udyan": {"id": "sambhaji-udyan", "name": "Chhatrapati Sambhaji Udyan", "lat": 18.51850, "lng": 73.84610},
    "pmc": {"id": "pmc", "name": "PMC", "lat": 18.52040, "lng": 73.85670},
    "mangalwar-peth": {"id": "mangalwar-peth", "name": "Mangalwar Peth", "lat": 18.52650, "lng": 73.86640},
    "pune-railway-station": {"id": "pune-railway-station", "name": "Pune Railway Station", "lat": 18.52890, "lng": 73.87440},
    "ruby-hall-clinic": {"id": "ruby-hall-clinic", "name": "Ruby Hall Clinic", "lat": 18.53310, "lng": 73.87980},
    "bund-garden": {"id": "bund-garden", "name": "Bund Garden", "lat": 18.53620, "lng": 73.88330},
    "yerwada": {"id": "yerwada", "name": "Yerwada", "lat": 18.54710, "lng": 73.87870},
    "kalyani-nagar": {"id": "kalyani-nagar", "name": "Kalyani Nagar", "lat": 18.54850, "lng": 73.90050},
    "ramwadi": {"id": "ramwadi", "name": "Ramwadi", "lat": 18.55703, "lng": 73.90856},
}

LINES = [
    {
        "line_id": "purple",
        "line_name": "Purple Line · Line 1",
        "line_color": "#8A2BE2",
        "route_sequence": [
            "pcmc", "sant-tukaram-nagar", "bhosari", "kasarwadi", "phugewadi", "dapodi", "bopodi",
            "khadki", "range-hill", "shivajinagar", "civil-court", "budhwar-peth", "mandai", "swargate",
        ],
    },
    {
        "line_id": "aqua",
        "line_name": "Aqua Line · Line 2",
        "line_color": "#008B8B",
        "route_sequence": [
            "vanaz", "anand-nagar", "ideal-colony", "nal-stop", "garware-college", "deccan-gymkhana",
            "sambhaji-udyan", "pmc", "civil-court", "mangalwar-peth", "pune-railway-station",
            "ruby-hall-clinic", "bund-garden", "yerwada", "kalyani-nagar", "ramwadi",
        ],
    },
]


def build_network() -> dict[str, Any]:
    """Return the complete two-line network and the Civil Court interchange."""
    return {
        "network_name": "Pune Metro Phase I",
        "coordinate_source": "Curated public-map station-area anchors; approximate WGS84",
        "coordinate_accuracy_note": "Approximate station locations; not survey-grade platform coordinates.",
        "approximate_coordinates": True,
        "lines": LINES,
        "stations": list(STATIONS.values()),
        "interchanges": [{
            "station_id": "civil-court",
            "station_name": "Civil Court",
            "line_ids": ["purple", "aqua"],
            "transfer_penalty_min": 3.0,
        }],
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(build_network(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Wrote %d stations across %d lines to %s", len(STATIONS), len(LINES), OUTPUT_PATH)


if __name__ == "__main__":
    main()
