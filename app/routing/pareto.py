"""Four-objective Pareto filtering and preference labels."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from app.routing.candidates import RouteCandidate

PREFERENCE_TAGS = {
    "duration": "⚡ Fastest Route",
    "fare": "💰 Cheapest Route",
    "emissions": "🌱 Greenest Route",
    "walking": "👟 Least Walking",
    "balanced": "⚖️ Best Overall / Balanced",
}


class ParetoOptimizer:
    """Keep non-dominated options and label objective winners."""

    @staticmethod
    def _values(candidate: RouteCandidate) -> tuple[float, float, float, float]:
        return (
            candidate.total_duration_min,
            candidate.total_fare_inr,
            candidate.total_co2_grams,
            candidate.walk_distance_km,
        )

    @classmethod
    def dominates(cls, first: RouteCandidate, second: RouteCandidate) -> bool:
        left, right = cls._values(first), cls._values(second)
        return all(a <= b + 1e-9 for a, b in zip(left, right)) and any(a < b - 1e-9 for a, b in zip(left, right))

    @classmethod
    def frontier(cls, candidates: Iterable[RouteCandidate]) -> list[RouteCandidate]:
        rows = list(candidates)
        return [candidate for i, candidate in enumerate(rows)
                if not any(i != j and cls.dominates(other, candidate) for j, other in enumerate(rows))]

    @classmethod
    def optimize(cls, candidates: Iterable[RouteCandidate]) -> list[RouteCandidate]:
        rows = cls.frontier(candidates)
        if not rows:
            return []
        values = [cls._values(candidate) for candidate in rows]
        ranges = [(min(row[i] for row in values), max(row[i] for row in values)) for i in range(4)]

        def score(candidate: RouteCandidate) -> float:
            current = cls._values(candidate)
            normalized = [(current[i] - low) / (high - low) if high > low else 0.0
                          for i, (low, high) in enumerate(ranges)]
            return sum(normalized) / len(normalized)

        winner_values = [min(row[i] for row in values) for i in range(4)]
        optimized = []
        for candidate in rows:
            current = cls._values(candidate)
            tags = [PREFERENCE_TAGS[key] for i, key in enumerate(("duration", "fare", "emissions", "walking"))
                    if abs(current[i] - winner_values[i]) <= 1e-9]
            if abs(score(candidate) - min(score(item) for item in rows)) <= 1e-9:
                tags.append(PREFERENCE_TAGS["balanced"])
            response = candidate.response.model_copy(update={"preference_tags": tags})
            optimized.append(replace(candidate, response=response))
        optimized.sort(key=lambda item: (score(item), item.total_duration_min, item.total_fare_inr, item.candidate_id))
        return optimized


pareto_optimizer = ParetoOptimizer()
