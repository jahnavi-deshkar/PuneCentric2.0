"""FastAPI integration tests for the supported route-planning modes."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def request_body(origin: tuple[float, float], destination: tuple[float, float]) -> dict:
    return {
        "origin": {"lat": origin[0], "lng": origin[1]},
        "destination": {"lat": destination[0], "lng": destination[1]},
    }


def assert_route_metrics(route: dict) -> None:
    assert route["total_distance_km"] >= 0
    assert route["total_duration_min"] >= 0
    assert route["total_fare_inr"] >= 0
    assert route["total_co2_grams"] >= 0
    assert isinstance(route["legs"], list) and route["legs"]
    for leg in route["legs"]:
        assert leg["distance_km"] >= 0
        assert leg["duration_min"] >= 0
        assert isinstance(leg["geometry"], list)


def test_walking_endpoint_returns_polyline_and_metrics() -> None:
    response = client.post(
        "/api/routes/walking",
        json=request_body((18.5204, 73.8567), (18.5314, 73.8446)),
    )

    assert response.status_code == 200, response.text
    route = response.json()
    assert route["mode"] == "walking"
    assert_route_metrics(route)
    assert len(route["legs"][0]["geometry"]) >= 2


def test_bus_endpoint_returns_pmpml_route() -> None:
    response = client.post(
        "/api/routes/bus",
        json=request_body((18.5018, 73.8636), (18.4575, 73.8675)),
    )

    assert response.status_code == 200, response.text
    route = response.json()
    assert route["mode"] == "bus"
    assert_route_metrics(route)
    assert any(leg["mode"] == "bus" and leg.get("board_stop") and leg.get("alight_stop") for leg in route["legs"])


def test_metro_endpoint_returns_station_route() -> None:
    response = client.post(
        "/api/routes/metro",
        json=request_body((18.5071, 73.80527), (18.55703, 73.90856)),
    )

    assert response.status_code == 200, response.text
    route = response.json()
    assert route["mode"] == "metro"
    assert_route_metrics(route)
    assert any(leg["mode"] == "metro" and leg.get("board_station") and leg.get("alight_station") for leg in route["legs"])


def test_auto_endpoint_returns_direct_auto_leg() -> None:
    response = client.post(
        "/api/routes/auto",
        json=request_body((18.5204, 73.8567), (18.5314, 73.8446)),
    )

    assert response.status_code == 200, response.text
    route = response.json()
    assert route["mode"] == "auto"
    assert_route_metrics(route)
    assert len(route["legs"]) == 1
    assert route["legs"][0]["mode"] == "auto"
    assert len(route["legs"][0]["geometry"]) >= 2


def test_multimodal_endpoint_accepts_constraints_and_returns_pareto_options() -> None:
    body = request_body((18.5018, 73.8636), (18.4575, 73.8675))
    body["constraints"] = {
        "max_budget_inr": 100.0,
        "max_walk_distance_km": 2.0,
        "max_transfers": 2,
    }

    response = client.post("/api/routes/multimodal", json=body)

    assert response.status_code == 200, response.text
    routes = response.json()
    assert isinstance(routes, list) and routes
    for route in routes:
        assert_route_metrics(route)
        assert route["total_fare_inr"] <= 100.0
        assert route["walk_distance_km"] <= 2.0
        assert route["transfers_count"] <= 2
        assert isinstance(route["preference_tags"], list)
    assert any(route["preference_tags"] for route in routes)
