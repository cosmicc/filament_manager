"""Immutable filament-cost calculations for current and historical print snapshots."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from filament_manager.models.printing import PrintJob, PrintMaterialSegment

COST_QUANTUM = Decimal("0.01")


def _decimal(value: object) -> Decimal | None:
    """Parse one finite decimal snapshot value."""

    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def snapshot_cost_basis(snapshot: dict[str, Any]) -> tuple[Decimal, str] | None:
    """Return the captured spool cost basis without consulting mutable inventory."""

    spool = snapshot.get("spool")
    if not isinstance(spool, dict):
        return None
    cost_per_gram = _decimal(spool.get("cost_per_gram"))
    currency = spool.get("currency")
    if (
        cost_per_gram is None
        or cost_per_gram < 0
        or not isinstance(currency, str)
        or len(currency) != 3
        or not currency.isalpha()
    ):
        return None
    return cost_per_gram, currency.upper()


def segment_cost(segment: PrintMaterialSegment) -> tuple[Decimal, Decimal, str] | None:
    """Return cost per gram, actual segment cost, and currency when fully known."""

    if segment.actual_filament_weight_g is None:
        return None
    basis = snapshot_cost_basis(segment.state_snapshot)
    if basis is None:
        return None
    cost_per_gram, currency = basis
    return (
        cost_per_gram,
        (segment.actual_filament_weight_g * cost_per_gram).quantize(
            COST_QUANTUM,
            rounding=ROUND_HALF_UP,
        ),
        currency,
    )


def print_cost_summary(job: PrintJob) -> dict[str, object]:
    """Calculate actual and predicted cost with explicit partial/mixed-currency state."""

    weighted_segments = [segment for segment in job.segments if segment.actual_filament_weight_g is not None]
    actual_weight = sum(
        (segment.actual_filament_weight_g or Decimal("0") for segment in weighted_segments),
        Decimal("0"),
    )
    priced: list[tuple[Decimal, Decimal, str]] = []
    priced_weight = Decimal("0")
    for segment in weighted_segments:
        cost = segment_cost(segment)
        if cost is None:
            continue
        priced.append(cost)
        priced_weight += segment.actual_filament_weight_g or Decimal("0")

    if not weighted_segments and job.actual_filament_weight_g is not None:
        basis = snapshot_cost_basis(job.state_snapshot)
        actual_weight = job.actual_filament_weight_g
        if basis is not None:
            cost_per_gram, basis_currency = basis
            priced = [
                (
                    cost_per_gram,
                    (actual_weight * cost_per_gram).quantize(
                        COST_QUANTUM,
                        rounding=ROUND_HALF_UP,
                    ),
                    basis_currency,
                )
            ]
            priced_weight = actual_weight

    currencies = {item[2] for item in priced}
    currency_conflict = len(currencies) > 1
    currency: str | None = next(iter(currencies)) if len(currencies) == 1 else None
    actual_cost = (
        sum((item[1] for item in priced), Decimal("0")).quantize(
            COST_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        if currency is not None and priced
        else None
    )
    complete = bool(actual_weight > 0 and priced_weight == actual_weight and currency is not None)

    predicted_cost: Decimal | None = None
    predicted_basis = snapshot_cost_basis(job.state_snapshot)
    if not currency_conflict and job.predicted_filament_weight_g is not None and predicted_basis is not None:
        predicted_rate, predicted_currency = predicted_basis
        if currency is None or predicted_currency == currency:
            currency = currency or predicted_currency
            predicted_cost = (job.predicted_filament_weight_g * predicted_rate).quantize(
                COST_QUANTUM,
                rounding=ROUND_HALF_UP,
            )

    return {
        "actual_filament_cost": actual_cost,
        "predicted_filament_cost": predicted_cost,
        "cost_currency": currency,
        "cost_currency_conflict": currency_conflict,
        "cost_complete": complete,
        "priced_filament_weight_g": priced_weight,
        "unpriced_filament_weight_g": max(Decimal("0"), actual_weight - priced_weight),
    }
