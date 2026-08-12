"""Import all models so Alembic can discover the complete metadata."""

from .auth import User, UserSession
from .base import Base
from .calibration import CalibrationSession, CalibrationStep
from .inventory import (
    BuildPlate,
    BuildPlateSurface,
    FilamentColor,
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
    Spool,
    SpoolMeasurement,
    SpoolUsageEvent,
    Vendor,
)
from .operations import AuditEvent, Device, ImportRun, NfcTag, OutboxJob, ProjectionState
from .workstations import CuraDeployment, WorkstationAgent, WorkstationPairingCode

__all__ = [
    "AuditEvent",
    "Base",
    "BuildPlate",
    "BuildPlateSurface",
    "CalibrationSession",
    "CalibrationStep",
    "CuraDeployment",
    "Device",
    "FilamentColor",
    "FilamentProduct",
    "ImportRun",
    "MaterialProfile",
    "MaterialTemplate",
    "MaterialTemplateRevision",
    "NfcTag",
    "OutboxJob",
    "Printer",
    "ProjectionState",
    "Spool",
    "SpoolMeasurement",
    "SpoolUsageEvent",
    "User",
    "UserSession",
    "Vendor",
    "WorkstationAgent",
    "WorkstationPairingCode",
]
