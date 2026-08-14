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
from .operations import (
    ApplicationSetting,
    AuditEvent,
    BuildPlateMaintenanceEvent,
    Device,
    ImportRun,
    NfcTag,
    Notification,
    OutboxJob,
    ProjectionState,
    UserNotificationState,
)
from .printing import PrintAssessment, PrintJob, PrintMaterialSegment
from .workstations import (
    CuraDeployment,
    CuraManagedEditReceipt,
    WorkstationAgent,
    WorkstationPairingCode,
)

__all__ = [
    "ApplicationSetting",
    "AuditEvent",
    "Base",
    "BuildPlate",
    "BuildPlateMaintenanceEvent",
    "BuildPlateSurface",
    "CalibrationSession",
    "CalibrationStep",
    "CuraDeployment",
    "CuraManagedEditReceipt",
    "Device",
    "FilamentColor",
    "FilamentProduct",
    "ImportRun",
    "MaterialProfile",
    "MaterialTemplate",
    "MaterialTemplateRevision",
    "NfcTag",
    "Notification",
    "OutboxJob",
    "PrintAssessment",
    "PrintJob",
    "PrintMaterialSegment",
    "Printer",
    "ProjectionState",
    "Spool",
    "SpoolMeasurement",
    "SpoolUsageEvent",
    "User",
    "UserNotificationState",
    "UserSession",
    "Vendor",
    "WorkstationAgent",
    "WorkstationPairingCode",
]
