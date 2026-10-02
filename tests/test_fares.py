"""Unit coverage for Pune mode fare slabs and discounts."""

import pytest

from app.calculations.fares import FareEngine


@pytest.fixture
def fares() -> FareEngine:
    return FareEngine()


def test_walking_is_free(fares: FareEngine) -> None:
    assert fares.walking().total_fare == 0.00


@pytest.mark.parametrize(
    ("distance_km", "expected"),
    [(1.5, 5.0), (5.0, 10.0), (10.0, 15.0), (22.0, 25.0)],
)
def test_bus_stage_fare_slabs(fares: FareEngine, distance_km: float, expected: float) -> None:
    assert fares.bus(distance_km).total_fare == expected


def test_bus_daily_pass_is_flat_seventy_rupees(fares: FareEngine) -> None:
    fare = fares.bus(22.0, daily_pass=True)
    assert fare.total_fare == 70.0
    assert fare.base_fare == 70.0
    assert fare.distance_fare == 0.0


@pytest.mark.parametrize(
    ("distance_km", "expected"),
    [(1.5, 10.0), (4.0, 20.0), (8.0, 30.0), (15.0, 35.0)],
)
def test_metro_distance_slabs(fares: FareEngine, distance_km: float, expected: float) -> None:
    assert fares.metro(distance_km).total_fare == expected


def test_metro_weekend_discount(fares: FareEngine) -> None:
    fare = fares.metro(4.0, weekend=True)
    assert fare.total_fare == 14.0
    assert fare.discounts == 6.0
    assert fare.discount_details["weekend"] == 6.0


def test_metro_student_discount(fares: FareEngine) -> None:
    fare = fares.metro(8.0, student=True)
    assert fare.total_fare == 21.0
    assert fare.discounts == 9.0
    assert fare.discount_details["student"] == 9.0


def test_metro_weekend_and_student_discounts_apply_sequentially(fares: FareEngine) -> None:
    fare = fares.metro(15.0, weekend=True, student=True)
    assert fare.total_fare == 17.15
    assert fare.discounts == 17.85


def test_auto_rickshaw_september_2026_tariff(fares: FareEngine) -> None:
    at_base_distance = fares.auto(1.5, night_surcharge=False)
    beyond_base_distance = fares.auto(3.5, night_surcharge=False)
    assert at_base_distance.base_fare == 30.0
    assert at_base_distance.distance_fare == 0.0
    assert at_base_distance.total_fare == 30.0
    assert beyond_base_distance.base_fare == 30.0
    assert beyond_base_distance.distance_fare == 40.0
    assert beyond_base_distance.total_fare == 70.0


def test_auto_night_surcharge_is_twenty_five_percent(fares: FareEngine) -> None:
    fare = fares.auto(3.5, night_surcharge=True)
    assert fare.surcharges == 17.5
    assert fare.surcharge_details["night_surcharge"] == 17.5
    assert fare.total_fare == 87.5
