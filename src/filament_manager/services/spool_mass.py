"""Re-evaluate immutable gross observations against the current empty-spool tare."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.domain.mass import GRAM, InvalidWeightError
from filament_manager.models.enums import MeasurementStatus
from filament_manager.models.inventory import Spool, SpoolMeasurement, SpoolUsageEvent


@dataclass(frozen=True)
class SpoolMassBasis:
    """A retained scale reading and subsequent signed consumption/corrections."""

    gross_mass_g: Decimal
    adjustment_g: Decimal

    def remaining(self, tare_mass_g: Decimal) -> Decimal:
        """Apply today's tare without rewriting evidence or restoring consumed mass."""

        if tare_mass_g > self.gross_mass_g:
            raise InvalidWeightError("Empty spool weight cannot exceed the last total scale weight")
        return max(Decimal("0"), self.gross_mass_g - tare_mass_g + self.adjustment_g).quantize(GRAM)


async def spool_mass_basis(session: AsyncSession, spool: Spool) -> SpoolMassBasis | None:
    """Read the latest accepted observation and all changes applied after it.

    Creation time is the transaction boundary: a backdated observation was still
    accepted as a new baseline when entered. Tare recalculations are not physical
    consumption and must not be counted again on subsequent edits. Signed manual
    corrections remain explicit offsets from this baseline.
    """

    measurement = await session.scalar(
        select(SpoolMeasurement)
        .where(SpoolMeasurement.spool_id == spool.id, SpoolMeasurement.status == MeasurementStatus.ACCEPTED)
        .order_by(SpoolMeasurement.created_at.desc(), SpoolMeasurement.id.desc())
        .limit(1)
    )
    if measurement is None:
        return None
    adjustment = await session.scalar(
        select(func.coalesce(func.sum(SpoolUsageEvent.mass_delta_g), 0)).where(
            SpoolUsageEvent.spool_id == spool.id,
            SpoolUsageEvent.created_at > measurement.created_at,
            SpoolUsageEvent.source != "tare_correction",
        )
    )
    return SpoolMassBasis(measurement.gross_mass_g, Decimal(adjustment or 0))
