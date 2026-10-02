"""Unit coverage for passenger emission factors and equivalencies."""

import pytest

from app.calculations.emissions import EmissionEngine


@pytest.fixture
def emissions() -> EmissionEngine:
    return EmissionEngine()


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("walking", 0.0), ("metro", 15.0), ("bus", 35.0), ("auto", 70.0), ("car", 120.0)],
)
def test_per_mode_emissions_per_kilometer(emissions: EmissionEngine, mode: str, expected: float) -> None:
    assert emissions.emissions(mode, 1.0) == expected


def test_car_emissions_savings(emissions: EmissionEngine) -> None:
    assert emissions.calculate_savings("metro", 2.0) == 210.0
    assert emissions.calculate_savings("walking", 2.0) == 240.0


def test_equivalencies_use_configured_tree_and_phone_factors(emissions: EmissionEngine) -> None:
    equivalencies = emissions.equivalencies(210.0)
    assert equivalencies["tree_days"] == pytest.approx(210.0 / 59.0, abs=0.01)
    assert equivalencies["smartphone_charges"] == pytest.approx(210.0 / 8.22, abs=0.01)


def test_negative_savings_do_not_report_negative_equivalencies(emissions: EmissionEngine) -> None:
    assert emissions.equivalencies(-10.0) == {"smartphone_charges": 0.0, "tree_days": 0.0}
