"""Unit coverage for hard constraints and the four-objective Pareto frontier."""

from app.models.route import RouteConstraints, RouteResponse
from app.routing.candidates import RouteCandidate
from app.routing.constraints import ConstraintFilter
from app.routing.pareto import ParetoOptimizer


def candidate(
    candidate_id: str,
    *,
    duration: float,
    fare: float,
    co2: float,
    walking: float,
    transfers: int = 0,
) -> RouteCandidate:
    response = RouteResponse(
        mode="multimodal",
        total_distance_km=4.0,
        total_duration_min=duration,
        total_fare_inr=fare,
        total_co2_grams=co2,
        legs=[],
        candidate_id=candidate_id,
        transfers_count=transfers,
        walk_distance_km=walking,
    )
    return RouteCandidate(
        candidate_id=candidate_id,
        candidate_name=candidate_id,
        response=response,
        total_distance_km=4.0,
        total_duration_min=duration,
        total_fare_inr=fare,
        total_co2_grams=co2,
        transfers_count=transfers,
        walk_distance_km=walking,
    )


def test_constraint_filter_rejects_candidates_over_each_active_limit() -> None:
    routes = [
        candidate("within", duration=20, fare=40, co2=60, walking=1.0, transfers=1),
        candidate("over-budget", duration=20, fare=101, co2=60, walking=1.0, transfers=1),
        candidate("over-walk", duration=20, fare=40, co2=60, walking=2.1, transfers=1),
        candidate("over-transfers", duration=20, fare=40, co2=60, walking=1.0, transfers=3),
    ]
    limits = RouteConstraints(max_budget_inr=100, max_walk_distance_km=2, max_transfers=2)
    filtered = ConstraintFilter.filter_candidates(routes, limits)
    assert [route.candidate_id for route in filtered] == ["within"]


def test_constraint_filter_keeps_routes_on_inclusive_limits() -> None:
    route = candidate("edge", duration=20, fare=100, co2=60, walking=2, transfers=2)
    assert ConstraintFilter.filter_candidates(
        [route], RouteConstraints(max_budget_inr=100, max_walk_distance_km=2, max_transfers=2)
    ) == [route]


def test_pareto_frontier_discards_dominated_routes() -> None:
    best = candidate("best", duration=20, fare=10, co2=50, walking=0.5)
    dominated = candidate("dominated", duration=25, fare=15, co2=70, walking=1.0)
    faster_tradeoff = candidate("fast", duration=15, fare=25, co2=90, walking=0.8)
    optimizer = ParetoOptimizer()

    frontier = optimizer.frontier([best, dominated, faster_tradeoff])

    assert {route.candidate_id for route in frontier} == {"best", "fast"}
    assert optimizer.dominates(best, dominated)
    assert not optimizer.dominates(best, faster_tradeoff)


def test_pareto_optimizer_assigns_each_preference_tag() -> None:
    routes = [
        candidate("fastest", duration=10, fare=40, co2=100, walking=2),
        candidate("cheapest", duration=40, fare=5, co2=100, walking=2),
        candidate("greenest", duration=40, fare=40, co2=10, walking=2),
        candidate("least-walk", duration=40, fare=40, co2=100, walking=0.1),
    ]

    optimized = ParetoOptimizer.optimize(routes)
    tags_by_id = {route.candidate_id: set(route.response.preference_tags) for route in optimized}
    all_tags = set().union(*tags_by_id.values())

    assert "⚡ Fastest Route" in tags_by_id["fastest"]
    assert "💰 Cheapest Route" in tags_by_id["cheapest"]
    assert "🌱 Greenest Route" in tags_by_id["greenest"]
    assert "👟 Least Walking" in tags_by_id["least-walk"]
    assert "⚖️ Best Overall / Balanced" in all_tags


def test_pareto_empty_input_returns_empty_frontier() -> None:
    assert ParetoOptimizer.optimize([]) == []
