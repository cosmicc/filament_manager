"""Import all models so Alembic can discover the complete metadata."""

from .auth import User, UserSession
from .base import Base
from .calibration import CalibrationSession, CalibrationStep
from .inventory import (
    BuildPlate,
    FilamentProduct,
    MaterialProfile,
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
    "CalibrationSession",
    "CalibrationStep",
    "CuraDeployment",
    "Device",
    "FilamentProduct",
    "ImportRun",
    "MaterialProfile",
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
