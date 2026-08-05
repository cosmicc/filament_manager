"""Canonical spool mass calculations and acceptance policy."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from filament_manager.models.enums import SpoolStatus

GRAM = Decimal("0.001")
HUNDRED = Decimal("100")


class InvalidWeightError(ValueError):
    """Raised when a measurement violates a physical constraint."""


class MeasurementConfirmationRequired(ValueError):
    """Raised when a suspicious increase was not explicitly confirmed."""


@dataclass(frozen=True)
class MeasurementCalculation:
    """The deterministic result of evaluating a gross-weight observation."""

    net_mass_g: Decimal
    variance_g: Decimal
    remaining_percent: Decimal
    requires_confirmation: bool
    spool_status: SpoolStatus


def _grams(value: Decimal) -> Decimal:
    return value.quantize(GRAM, rounding=ROUND_HALF_UP)


def status_for_mass(remaining_g: Decimal, nominal_g: Decimal, low_threshold_percent: Decimal) -> SpoolStatus:
    """Classify inventory status from canonical effective mass."""

    if remaining_g <= 0:
        return SpoolStatus.EMPTY
    percent = (remaining_g / nominal_g) * HUNDRED
    if percent < low_threshold_percent:
        return SpoolStatus.LOW
    return SpoolStatus.IN_STOCK


def calculate_measurement(
    *,
    gross_mass_g: Decimal,
    tare_mass_g: Decimal,
    nominal_mass_g: Decimal,
    expected_remaining_g: Decimal,
    low_threshold_percent: Decimal,
    increase_tolerance_percent: Decimal,
    increase_tolerance_g: Decimal,
    confirmed: bool,
    allow_above_nominal: bool = False,
) -> MeasurementCalculation:
    """Validate and calculate a manual or accepted scale measurement.

    The observation never rewrites usage history. It records variance from the
    current expectation and becomes the new physical correction only after all
    confirmation and physical-bound checks pass.
    """

    if gross_mass_g < 0 or tare_mass_g < 0:
        raise InvalidWeightError("gross and tare mass must be non-negative")
    if nominal_mass_g <= 0:
        raise InvalidWeightError("nominal mass must be positive")
    if gross_mass_g < tare_mass_g:
        raise InvalidWeightError("gross mass cannot be below tare mass")

    net_mass = _grams(gross_mass_g - tare_mass_g)
    if net_mass > nominal_mass_g and not allow_above_nominal:
        raise InvalidWeightError("remaining mass exceeds nominal capacity")

    variance = _grams(net_mass - expected_remaining_g)
    percent_tolerance = _grams(expected_remaining_g * increase_tolerance_percent / HUNDRED)
    required_tolerance = max(increase_tolerance_g, percent_tolerance)
    requires_confirmation = variance > required_tolerance
    if requires_confirmation and not confirmed:
        raise MeasurementConfirmationRequired(
            "remaining mass increased beyond the configured confirmation threshold"
        )

    percent = _grams((net_mass / nominal_mass_g) * HUNDRED)
    return MeasurementCalculation(
        net_mass_g=net_mass,
        variance_g=variance,
        remaining_percent=percent,
        requires_confirmation=requires_confirmation,
        spool_status=status_for_mass(net_mass, nominal_mass_g, low_threshold_percent),
    )


def estimated_length_m(remaining_mass_g: Decimal, density_g_cm3: Decimal, diameter_mm: Decimal) -> Decimal:
    """Estimate filament length from mass, density, and circular cross-section."""

    if remaining_mass_g < 0 or density_g_cm3 <= 0 or diameter_mm <= 0:
        raise ValueError("mass must be non-negative and density/diameter must be positive")
    pi = Decimal("3.14159265358979323846")
    radius_cm = diameter_mm / Decimal("20")
    cross_section_cm2 = pi * radius_cm * radius_cm
    length_cm = remaining_mass_g / (density_g_cm3 * cross_section_cm2)
    return (length_cm / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
