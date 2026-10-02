"""Hard constraint filtering for generated route candidates."""

from __future__ import annotations

from typing import Any, Iterable

from app.models.route import RouteConstraints


class ConstraintFilter:
    """Remove routes that violate any active user constraint."""

    @staticmethod
    def filter_candidates(candidates: Iterable[Any], constraints: RouteConstraints | dict | None) -> list[Any]:
        if constraints is None:
            limits = RouteConstraints()
        elif isinstance(constraints, RouteConstraints):
            limits = constraints
        else:
            limits = RouteConstraints.model_validate(constraints)

        kept = []
        for candidate in candidates:
            if limits.max_budget_inr is not None and candidate.total_fare_inr > limits.max_budget_inr + 1e-9:
                continue
            if limits.max_walk_distance_km is not None and candidate.walk_distance_km > limits.max_walk_distance_km + 1e-9:
                continue
            if limits.max_transfers is not None and candidate.transfers_count > limits.max_transfers:
                continue
            kept.append(candidate)
        return kept


constraint_filter = ConstraintFilter()
