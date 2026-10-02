"""Extract Pune boundaries, localities, and points of interest from OSM.

Run from the repository root with ``python scripts/extract_pune_osm.py``.
Each layer is queried independently. If Overpass is unavailable or returns no
usable features, a clearly labelled seed layer is written for offline use.
Seed coordinates are approximate map-search anchors, not surveyed boundaries.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import Point, box, mapping

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES_DIR = ROOT / "data" / "boundaries"
LOCALITIES_DIR = ROOT / "data" / "localities"
POIS_DIR = ROOT / "data" / "pois"
LOGGER = logging.getLogger("pune_osm")

# Approximate centers provide useful offline search/map anchors. The small
# bounding boxes are display/search extents, not authoritative area borders.
SEED_LOCALITIES: list[dict[str, Any]] = [
    {"name": "Shaniwar Peth", "category": "peth", "locality": "Shaniwar Peth", "lat": 18.5196, "lng": 73.8553},
    {"name": "Sadashiv Peth", "category": "peth", "locality": "Sadashiv Peth", "lat": 18.5089, "lng": 73.8478},
    {"name": "Kasba Peth", "category": "peth", "locality": "Kasba Peth", "lat": 18.5209, "lng": 73.8585},
    {"name": "Narayan Peth", "category": "peth", "locality": "Narayan Peth", "lat": 18.5125, "lng": 73.8500},
    {"name": "Raviwar Peth", "category": "peth", "locality": "Raviwar Peth", "lat": 18.5155, "lng": 73.8595},
    {"name": "Budhwar Peth", "category": "peth", "locality": "Budhwar Peth", "lat": 18.5167, "lng": 73.8544},
    {"name": "Camp", "category": "locality", "locality": "Camp", "lat": 18.5137, "lng": 73.8790},
    {"name": "Deccan Gymkhana", "category": "locality", "locality": "Deccan Gymkhana", "lat": 18.5164, "lng": 73.8400},
    {"name": "Kothrud", "category": "locality", "locality": "Kothrud", "lat": 18.5074, "lng": 73.8077},
    {"name": "Viman Nagar", "category": "locality", "locality": "Viman Nagar", "lat": 18.5679, "lng": 73.9143},
    {"name": "Hinjewadi", "category": "locality", "locality": "Hinjewadi", "lat": 18.5913, "lng": 73.7389},
    {"name": "Hadapsar", "category": "locality", "locality": "Hadapsar", "lat": 18.5089, "lng": 73.9260},
    {"name": "Koregaon Park", "category": "locality", "locality": "Koregaon Park", "lat": 18.5362, "lng": 73.8939},
    {"name": "Aundh", "category": "locality", "locality": "Aundh", "lat": 18.5590, "lng": 73.8077},
    {"name": "Baner", "category": "locality", "locality": "Baner", "lat": 18.5590, "lng": 73.7868},
    {"name": "Wakad", "category": "locality", "locality": "Wakad", "lat": 18.5995, "lng": 73.7625},
    {"name": "Pimpri", "category": "locality", "locality": "Pimpri", "lat": 18.6298, "lng": 73.7997},
    {"name": "Chinchwad", "category": "locality", "locality": "Chinchwad", "lat": 18.6405, "lng": 73.7997},
    {"name": "Pune Municipal Corporation", "category": "boundary", "locality": "Pune", "lat": 18.5204, "lng": 73.8567},
    {"name": "Pimpri-Chinchwad Municipal Corporation", "category": "boundary", "locality": "Pimpri-Chinchwad", "lat": 18.6298, "lng": 73.7997},
]

SEED_POIS: list[dict[str, Any]] = [
    {"name": "Shaniwar Wada", "category": "heritage", "locality": "Shaniwar Peth", "lat": 18.5196, "lng": 73.8553},
    {"name": "Kayani Bakery", "category": "eatery", "locality": "Camp", "lat": 18.5133, "lng": 73.8790},
    {"name": "Chitale Bandhu (Deccan)", "category": "shop", "locality": "Deccan Gymkhana", "lat": 18.5161, "lng": 73.8410},
    {"name": "Tulshibaug", "category": "market", "locality": "Budhwar Peth", "lat": 18.5126, "lng": 73.8554},
    {"name": "Amanora Park Town", "category": "society", "locality": "Hadapsar", "lat": 18.5196, "lng": 73.9370},
    {"name": "Magarpatta City", "category": "society", "locality": "Hadapsar", "lat": 18.5167, "lng": 73.9270},
    {"name": "Blue Ridge", "category": "society", "locality": "Hinjewadi", "lat": 18.5890, "lng": 73.7060},
    {"name": "Dagdusheth Halwai Ganpati Temple", "category": "temple", "locality": "Budhwar Peth", "lat": 18.5165, "lng": 73.8560},
    {"name": "Aga Khan Palace", "category": "heritage", "locality": "Kalyani Nagar", "lat": 18.5527, "lng": 73.9015},
    {"name": "Sinhagad Fort", "category": "tourism", "locality": "Sinhagad", "lat": 18.3663, "lng": 73.7559},
    {"name": "Pune Railway Station", "category": "transport", "locality": "Sangamvadi", "lat": 18.5289, "lng": 73.8744},
    {"name": "Pune Okayama Friendship Garden", "category": "park", "locality": "Kothrud", "lat": 18.4854, "lng": 73.8070},
]


def _seed_feature(item: dict[str, Any], source: str) -> dict[str, Any]:
    lat, lng = float(item["lat"]), float(item["lng"])
    geometry = mapping(box(lng - 0.001, lat - 0.001, lng + 0.001, lat + 0.001)) if item["category"] in {"locality", "peth", "boundary"} else mapping(Point(lng, lat))
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "name": item["name"],
            "category": item["category"],
            "locality": item["locality"],
            "source": source,
            "is_seed": True,
        },
    }


def _write_seed(path: Path, records: list[dict[str, Any]], layer: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    collection = {
        "type": "FeatureCollection",
        "name": layer,
        "metadata": {"source": "seed data", "accuracy": "approximate; verify before operational use"},
        "features": [_seed_feature(row, "seed") for row in records],
    }
    path.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.warning("Wrote %d approximate seed features to %s", len(records), path)


def _write_gdf(frame: gpd.GeoDataFrame, path: Path, layer: str, category: str) -> None:
    frame = frame.copy()
    if frame.crs is None:
        frame = frame.set_crs("EPSG:4326")
    elif frame.crs.to_string() != "EPSG:4326":
        frame = frame.to_crs("EPSG:4326")
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
    if frame.empty:
        raise ValueError(f"No usable geometries in {layer}")
    if "name" not in frame.columns:
        frame["name"] = ""
    frame["category"] = frame.apply(lambda row: row.get("category") or category, axis=1)
    frame["locality"] = frame.apply(lambda row: row.get("locality") or row.get("name") or "Pune", axis=1)
    frame["source"] = "OpenStreetMap"
    frame["is_seed"] = False
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, driver="GeoJSON", index=False)
    LOGGER.info("Wrote %d OSM features to %s", len(frame), path)


def _query_places(queries: list[str], tags: dict[str, Any]) -> gpd.GeoDataFrame:
    """Try place names in order, returning first non-empty OSMnx result."""
    errors: list[str] = []
    for query in queries:
        try:
            frame = ox.features_from_place(query, tags=tags)
            if not frame.empty:
                return frame.reset_index()
        except Exception as exc:  # Network, geocoder, Overpass, and timeout fallback.
            errors.append(f"{query}: {exc}")
            LOGGER.warning("OSM query failed for %s: %s", query, exc)
    if errors:
        LOGGER.warning("All OSM queries failed for layer: %s", "; ".join(errors))
    return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


def extract_boundaries() -> None:
    output = BOUNDARIES_DIR / "pune_boundaries.geojson"
    query_specs = [
        ("Pune Municipal Corporation, Maharashtra, India", "Pune Municipal Corporation"),
        ("Pimpri-Chinchwad Municipal Corporation, Maharashtra, India", "Pimpri-Chinchwad Municipal Corporation"),
    ]
    frames = []
    for query, name in query_specs:
        frame = _query_places([query], {"boundary": "administrative", "name": name})
        if not frame.empty:
            frames.append(frame)
    frame = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326") if frames else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    if frame.empty:
        _write_seed(output, [row for row in SEED_LOCALITIES if row["category"] == "boundary"], "boundaries")
    else:
        _write_gdf(frame, output, "boundaries", "boundary")


def extract_localities() -> None:
    output = LOCALITIES_DIR / "pune_localities.geojson"
    names = [row["name"] for row in SEED_LOCALITIES if row["category"] == "peth"] + [
        "Kothrud", "Viman Nagar", "Hinjewadi", "Hadapsar", "Koregaon Park", "Aundh", "Baner", "Wakad"
    ]
    # OSMnx treats list-valued tags as OR. Exact-name requests help avoid
    # fetching unrelated objects across the full metropolitan region.
    frame = _query_places(
        ["Pune, Maharashtra, India"],
        {"place": ["suburb", "neighbourhood", "locality"], "name": names},
    )
    if frame.empty:
        _write_seed(output, SEED_LOCALITIES, "localities")
    else:
        _write_gdf(frame, output, "localities", "locality")


def extract_pois() -> None:
    output = POIS_DIR / "pune_pois.geojson"
    names = [row["name"] for row in SEED_POIS]
    frame = _query_places(
        ["Pune, Maharashtra, India"],
        {"name": names},
    )
    if frame.empty:
        _write_seed(output, SEED_POIS, "pois")
    else:
        _write_gdf(frame, output, "pois", "poi")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # Keep request timeouts bounded. A failed layer independently receives
    # seed data, so a partial Overpass outage does not block extraction.
    ox.settings.timeout = 45
    ox.settings.use_cache = True
    for extract in (extract_boundaries, extract_localities, extract_pois):
        try:
            extract()
        except Exception:
            LOGGER.exception("Unexpected extraction error; writing offline seed layer")
            if extract is extract_boundaries:
                _write_seed(BOUNDARIES_DIR / "pune_boundaries.geojson", [r for r in SEED_LOCALITIES if r["category"] == "boundary"], "boundaries")
            elif extract is extract_localities:
                _write_seed(LOCALITIES_DIR / "pune_localities.geojson", SEED_LOCALITIES, "localities")
            else:
                _write_seed(POIS_DIR / "pune_pois.geojson", SEED_POIS, "pois")
    LOGGER.info("Extraction complete. Run scripts/build_search_index.py to build the search index.")


if __name__ == "__main__":
    main()
