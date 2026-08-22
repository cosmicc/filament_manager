"""Queue safe Cura machine-nozzle updates for managed workstations."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.enums import CuraDeploymentStatus
from filament_manager.models.inventory import Printer
from filament_manager.models.workstations import CuraDeployment, WorkstationAgent


async def queue_cura_nozzle_update(
    session: AsyncSession,
    *,
    printer: Printer,
    previous_diameter_mm: Decimal,
    requested_by: UUID,
) -> int:
    """Queue an exact existing-variant selection on every managed workstation."""

    if previous_diameter_mm == printer.nozzle_diameter_mm:
        return 0

    agents = list(
        await session.scalars(
            select(WorkstationAgent).where(
                WorkstationAgent.enabled.is_(True),
                WorkstationAgent.cura_management_enabled.is_(True),
            )
        )
    )
    now = datetime.now(UTC)
    queued = 0
    for agent in agents:
        payload: dict[str, object] = {
            "operation": "nozzle_update",
            "printer_id": str(printer.id),
            "printer_code": printer.printer_code,
            "printer_name": printer.name,
            "previous_nozzle_diameter_mm": format(previous_diameter_mm, "f"),
            "nozzle_diameter_mm": format(printer.nozzle_diameter_mm, "f"),
        }
        checksum = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        idempotency_key = f"cura-nozzle:{agent.id}:{printer.id}:v{printer.record_version}"
        existing = await session.scalar(
            select(CuraDeployment.id).where(CuraDeployment.idempotency_key == idempotency_key)
        )
        if existing is not None:
            continue
        session.add(
            CuraDeployment(
                agent_id=agent.id,
                material_profile_id=None,
                requested_by=requested_by,
                status=CuraDeploymentStatus.PENDING,
                payload=payload,
                profile_checksum=checksum,
                idempotency_key=idempotency_key,
                attempts=0,
                next_attempt_at=now,
                result={},
                created_at=now,
                updated_at=now,
            )
        )
        queued += 1
    return queued
