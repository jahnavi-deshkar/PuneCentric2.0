"""Centralized, configurable fare calculations for Pune transport modes."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

from app.models.route import FareBreakdown

PUNE_TIMEZONE = ZoneInfo("Asia/Kolkata")


class FareEngine:
    """Calculate itemized INR fares; tariff values can be overridden at runtime.

    ``tariffs`` accepts partial mode dictionaries, allowing RTO/agency updates
    to be loaded from configuration without changing route solver code.
    """

    DEFAULT_TARIFFS: dict[str, dict[str, object]] = {
        "walking": {},
        "bus": {
            "slabs": ((2.0, 5.0), (8.0, 10.0), (14.0, 15.0), (20.0, 20.0), (float("inf"), 25.0)),
            "daily_pass": 70.0,
        },
        "metro": {
            "slabs": ((2.0, 10.0), (6.0, 20.0), (12.0, 30.0), (float("inf"), 35.0)),
            "weekend_discount_rate": 0.30,
            "student_discount_rate": 0.30,
        },
        "auto": {
            "base_distance_km": 1.5,
            "base_fare": 30.0,
            "per_km": 20.0,
            "night_surcharge_rate": 0.25,
            "night_start_hour": 0,
            "night_end_hour": 5,
        },
    }

    def __init__(self, tariffs: Mapping[str, Mapping[str, object]] | None = None) -> None:
        self.tariffs = {mode: dict(config) for mode, config in self.DEFAULT_TARIFFS.items()}
        for mode, config in (tariffs or {}).items():
            if mode not in self.tariffs:
                raise ValueError(f"Unsupported fare mode: {mode}")
            self.tariffs[mode].update(config)

    @staticmethod
    def _breakdown(
        mode: str,
        base: float = 0.0,
        distance: float = 0.0,
        surcharges: float = 0.0,
        discounts: float = 0.0,
        surcharge_details: dict[str, float] | None = None,
        discount_details: dict[str, float] | None = None,
    ) -> FareBreakdown:
        fields = [round(max(0.0, value), 2) for value in (base, distance, surcharges, discounts)]
        total = round(max(0.0, fields[0] + fields[1] + fields[2] - fields[3]), 2)
        return FareBreakdown(
            mode=mode,
            base_fare=fields[0],
            distance_fare=fields[1],
            surcharges=fields[2],
            discounts=fields[3],
            total_fare=total,
            currency="INR",
            surcharge_details={key: round(value, 2) for key, value in (surcharge_details or {}).items()},
            discount_details={key: round(value, 2) for key, value in (discount_details or {}).items()},
        )

    @classmethod
    def _slab_fare(cls, distance_km: float, slabs: object) -> float:
        if distance_km < 0:
            raise ValueError("Distance cannot be negative")
        for upper_bound, fare in slabs:  # type: ignore[union-attr]
            if distance_km <= float(upper_bound):
                return float(fare)
        return 0.0

    def zero(self, mode: str) -> FareBreakdown:
        """Return a zero-fare breakdown for walking, transfers, and free legs."""
        return self._breakdown(mode)

    def walking(self) -> FareBreakdown:
        return self.zero("walking")

    def bus(
        self,
        distance_km: float,
        *,
        daily_pass: bool = False,
        discount_rate: float = 0.0,
    ) -> FareBreakdown:
        """Return PMPML stage fare, with optional ₹70 daily-pass pricing."""
        config = self.tariffs["bus"]
        if daily_pass:
            gross = float(config["daily_pass"])
            base, distance = gross, 0.0
        else:
            gross = self._slab_fare(distance_km, config["slabs"])
            base, distance = min(5.0, gross), max(0.0, gross - 5.0)
        if not 0 <= discount_rate <= 1:
            raise ValueError("discount_rate must be between 0 and 1")
        discount = gross * discount_rate
        return self._breakdown("bus", base, distance, discounts=discount,
                               discount_details={"discount": discount} if discount else {})

    def metro(
        self,
        distance_km: float,
        *,
        weekend: bool = False,
        student: bool = False,
        student_discount_rate: float | None = None,
    ) -> FareBreakdown:
        """Return metro slab fare with optional weekend/student concessions.

        Discounts are applied sequentially to the remaining fare and never make
        the payable fare negative.
        """
        config = self.tariffs["metro"]
        gross = self._slab_fare(distance_km, config["slabs"])
        base, distance = min(10.0, gross), max(0.0, gross - 10.0)
        remaining = gross
        discount_parts: dict[str, float] = {}
        if weekend:
            rate = float(config["weekend_discount_rate"])
            amount = remaining * rate
            discount_parts["weekend"] = amount
            remaining -= amount
        if student:
            rate = float(config["student_discount_rate"] if student_discount_rate is None else student_discount_rate)
            if not 0 <= rate <= 1:
                raise ValueError("student_discount_rate must be between 0 and 1")
            amount = remaining * rate
            discount_parts["student"] = amount
        return self._breakdown("metro", base, distance,
                               discounts=sum(discount_parts.values()),
                               discount_details=discount_parts)

    @staticmethod
    def _is_night(now: datetime | None, start_hour: int, end_hour: int) -> bool:
        current = (now or datetime.now(PUNE_TIMEZONE)).astimezone(PUNE_TIMEZONE)
        return start_hour <= current.hour < end_hour

    def auto(self, distance_km: float, *, night_surcharge: bool | None = None,
             now: datetime | None = None) -> FareBreakdown:
        """Return the September 2026 Pune RTO fare, with optional night rate."""
        if distance_km < 0:
            raise ValueError("Distance cannot be negative")
        config = self.tariffs["auto"]
        if distance_km == 0:
            return self.zero("auto")
        base_distance = float(config["base_distance_km"])
        base = float(config["base_fare"])
        distance = max(0.0, distance_km - base_distance) * float(config["per_km"])
        is_night = self._is_night(now, int(config["night_start_hour"]), int(config["night_end_hour"]))
        apply_night = is_night if night_surcharge is None else night_surcharge
        surcharge = (base + distance) * float(config["night_surcharge_rate"]) if apply_night else 0.0
        return self._breakdown(
            "auto", base, distance, surcharges=surcharge,
            surcharge_details={"night_surcharge": surcharge},
        )

    def combine(self, breakdowns: Iterable[FareBreakdown], *, mode: str = "multimodal") -> FareBreakdown:
        """Aggregate leg fare components into a journey-level fare breakdown."""
        rows = list(breakdowns)
        surcharge_details: dict[str, float] = {}
        details: dict[str, float] = {}
        for row in rows:
            for key, value in row.surcharge_details.items():
                surcharge_details[key] = surcharge_details.get(key, 0.0) + value
            for key, value in row.discount_details.items():
                details[key] = details.get(key, 0.0) + value
        return self._breakdown(
            mode,
            base=sum(row.base_fare for row in rows),
            distance=sum(row.distance_fare for row in rows),
            surcharges=sum(row.surcharges for row in rows),
            discounts=sum(row.discounts for row in rows),
            surcharge_details=surcharge_details,
            discount_details=details,
        )


fare_engine = FareEngine()
