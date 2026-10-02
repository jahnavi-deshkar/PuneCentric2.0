"""FastAPI integration tests for the Pune location search endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_search_returns_matching_shaniwar_locations() -> None:
    response = client.get("/api/search", params={"q": "Shaniwar"})

    assert response.status_code == 200
    results = response.json()
    assert isinstance(results, list)
    assert results
    assert all("shaniwar" in row["name"].casefold() or "shaniwar" in row["locality"].casefold() for row in results)
    assert all({"id", "name", "category", "locality", "coordinates", "bounding_box"} <= row.keys() for row in results)


def test_locations_returns_pune_map_regions() -> None:
    response = client.get("/api/locations")

    assert response.status_code == 200
    regions = response.json()
    assert isinstance(regions, list)
    assert any(row["name"] == "Pune" for row in regions)
    assert any(row["name"] == "Pimpri-Chinchwad" for row in regions)
    assert all("lat" in row["coordinates"] and "lng" in row["coordinates"] for row in regions)
