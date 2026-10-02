"""Centralized passenger carbon estimates and ecological equivalents."""

from __future__ import annotations

from typing import Iterable, Mapping


class EmissionEngine:
    """Estimate transport emissions using configurable g CO₂/passenger-km factors."""

    DEFAULT_FACTORS_G_PER_KM = {
        "walking": 0.0,
        "metro": 15.0,
        "bus": 35.0,
        "auto": 70.0,
        "car": 120.0,
    }
    SMARTPHONE_CHARGE_G = 8.22
    TREE_ABSORPTION_G_PER_DAY = 59.0

    def __init__(self, factors_g_per_km: Mapping[str, float] | None = None) -> None:
        self.factors_g_per_km = dict(self.DEFAULT_FACTORS_G_PER_KM)
        for mode, factor in (factors_g_per_km or {}).items():
            if factor < 0:
                raise ValueError(f"Emission factor for {mode} cannot be negative")
            self.factors_g_per_km[mode.strip().lower()] = float(factor)

    @staticmethod
    def _mode_key(route_mode: str) -> str:
        mode = route_mode.strip().lower().replace("-", "_")
        aliases = {
            "walking": "walking", "walk": "walking", "pedestrian": "walking",
            "metro": "metro", "train": "metro", "electric_metro": "metro",
            "bus": "bus", "pmpml": "bus", "pmpml_bus": "bus",
            "auto": "auto", "autorickshaw": "auto", "auto_rickshaw": "auto", "cng_auto": "auto",
            "car": "car", "private_car": "car", "cab": "car", "taxi": "car",
        }
        if mode not in aliases:
            raise ValueError(f"No emission factor configured for mode: {route_mode}")
        return aliases[mode]

    def emissions(self, route_mode: str, distance_km: float) -> float:
        """Return estimated g CO₂ for a passenger over a leg or trip distance."""
        if distance_km < 0:
            raise ValueError("Distance cannot be negative")
        mode = self._mode_key(route_mode)
        try:
            factor = self.factors_g_per_km[mode]
        except KeyError as exc:
            raise ValueError(f"No emission factor configured for mode: {route_mode}") from exc
        return round(float(factor) * distance_km, 2)

    def calculate_savings(self, route_mode: str, distance_km: float) -> float:
        """Return grams avoided versus driving the same distance in a private car."""
        return round(self.emissions("car", distance_km) - self.emissions(route_mode, distance_km), 2)

    def equivalencies(self, co2_saved_grams: float) -> dict[str, float]:
        """Convert a CO₂ difference to phone charges and tree-days (estimates)."""
        avoided = max(0.0, co2_saved_grams)
        return {
            "smartphone_charges": round(avoided / self.SMARTPHONE_CHARGE_G, 2),
            "tree_days": round(avoided / self.TREE_ABSORPTION_G_PER_DAY, 2),
        }

    def leg_metrics(self, route_mode: str, distance_km: float) -> dict[str, float | str]:
        """Build the environmental fields shared by every route leg."""
        mode = self._mode_key(route_mode)
        co2 = self.emissions(mode, distance_km)
        saved = self.calculate_savings(mode, distance_km)
        equivalents = self.equivalencies(saved)
        intensity = self.factors_g_per_km[mode]
        if intensity == 0:
            badge = "🌱 Zero Emission"
        elif mode == "metro":
            badge = "⚡ Rapid & Clean"
        elif intensity <= 35:
            badge = "🌿 Low Carbon"
        elif saved > 0:
            badge = "🌿 Lower Carbon"
        else:
            badge = "🚗 Private Car Baseline"
        return {
            "co2_grams": co2,
            "co2_saved_grams": saved,
            "eco_badge": badge,
            "trees_equivalent": equivalents["tree_days"],
            "smartphone_charges_equivalent": equivalents["smartphone_charges"],
            "private_car_baseline_co2_grams": self.emissions("car", distance_km),
        }

    def route_metrics(self, legs: Iterable[object], total_distance_km: float) -> dict[str, float | str]:
        """Aggregate route legs and calculate savings against an equivalent car trip."""
        leg_rows = list(legs)
        co2 = round(sum(float(getattr(leg, "co2_grams", 0.0)) for leg in leg_rows), 2)
        baseline = self.emissions("car", total_distance_km)
        saved = round(baseline - co2, 2)
        equivalents = self.equivalencies(saved)
        if co2 <= 0:
            badge = "🌱 Zero Emission"
        elif total_distance_km > 0 and co2 / total_distance_km <= 15:
            badge = "⚡ Rapid & Clean"
        elif total_distance_km > 0 and co2 / total_distance_km <= 35:
            badge = "🌿 Low Carbon"
        elif saved > 0:
            badge = "🌿 Lower Carbon"
        else:
            badge = "🚗 Private Car Baseline"
        return {
            "total_co2_grams": co2,
            "co2_grams": co2,
            "co2_saved_grams": saved,
            "eco_badge": badge,
            "trees_equivalent": equivalents["tree_days"],
            "smartphone_charges_equivalent": equivalents["smartphone_charges"],
            "private_car_baseline_co2_grams": baseline,
        }


emission_engine = EmissionEngine()
