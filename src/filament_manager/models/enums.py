"""Database-backed domain enumerations."""

from enum import StrEnum


class UserRole(StrEnum):
    ADMINISTRATOR = "administrator"
    OPERATOR = "operator"
    VIEWER = "viewer"


class SpoolStatus(StrEnum):
    NEEDS_WEIGHING = "needs_weighing"
    IN_STOCK = "in_stock"
    LOW = "low"
    EMPTY = "empty"
    ARCHIVED = "archived"


class MeasurementSource(StrEnum):
    MANUAL = "manual"
    SCALE = "scale"
    IMPORT = "import"
    CORRECTION = "correction"


class MeasurementStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProfileStatus(StrEnum):
    DRAFT = "draft"
    CALIBRATION_IN_PROGRESS = "calibration_in_progress"
    VALIDATED = "validated"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class CalibrationStatus(StrEnum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


class CalibrationStepStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    SKIPPED = "skipped"


class PlateStatus(StrEnum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class PlateCondition(StrEnum):
    NEW = "new"
    GOOD = "good"
    WORN = "worn"
    DAMAGED = "damaged"
    RETIRED = "retired"


class PlateSurfaceTexture(StrEnum):
    """Supported physical finishes for one side of a build plate."""

    SMOOTH = "smooth"
    TEXTURED = "textured"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


class CuraDeploymentStatus(StrEnum):
    """Lifecycle states for a workstation Cura deployment."""

    PENDING = "pending"
    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
