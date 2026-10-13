"""Add durable material types and correct the approved carbon-fiber labels."""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a0678b901234"
down_revision = "ff567a890123"
branch_labels = None
depends_on = None

DEFAULT_NAMES = (
    "PLA",
    "PLA+",
    "Silk PLA",
    "PLA-CF",
    "PETG-CF",
    "PETG",
    "ASA",
    "ASA-CF",
    "ASA-GF",
    "ABS",
    "TPU",
    "PEBA",
    "PP",
    "PCTPE",
    "Nylon 645",
)
RENAMES = {"pla carbon fiber": "PLA-CF", "petg carbon fiber": "PETG-CF"}


def upgrade() -> None:
    """Retain settings and history; refuse ambiguous active scope collisions."""
    connection = op.get_bind()
    metadata = sa.MetaData()
    templates = sa.Table("material_templates", metadata, autoload_with=connection)
    products = sa.Table("filament_products", metadata, autoload_with=connection)
    audits = sa.Table("audit_events", metadata, autoload_with=connection)
    outbox = sa.Table("outbox_jobs", metadata, autoload_with=connection)
    rows = list(connection.execute(sa.select(templates)).mappings())
    scopes: set[tuple[object, str]] = set()
    for row in rows:
        if not row["active"]:
            continue
        target = RENAMES.get(row["material_type"].casefold(), row["material_type"])
        scope = (row["nozzle_id"], target.casefold())
        if scope in scopes:
            raise RuntimeError(
                "Material-type rename conflicts with an active nozzle template; resolve before upgrading"
            )
        scopes.add(scope)
    op.create_table(
        "material_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column("name_key", sa.String(144), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_material_types"),
        sa.UniqueConstraint("name_key", name="uq_material_types_name_key"),
    )
    catalog = sa.Table("material_types", metadata, autoload_with=connection)
    now = datetime.now(UTC)
    changed = False
    for table in (templates, products):
        for row in connection.execute(sa.select(table)).mappings():
            target = RENAMES.get(row["material_type"].casefold())
            if target is None:
                continue
            changed = True
            values = {"material_type": target, "record_version": row["record_version"] + 1, "updated_at": now}
            if table is templates:
                values["name"] = f"Template {target}"
            connection.execute(table.update().where(table.c.id == row["id"]).values(**values))
            connection.execute(
                audits.insert().values(
                    id=uuid4(),
                    source="migration",
                    action="material_type.label.correct",
                    object_type="material_template" if table is templates else "filament_product",
                    object_id=row["id"],
                    before={"material_type": row["material_type"]},
                    after={"material_type": target},
                    metadata={},
                    occurred_at=now,
                    correlation_id="upgrade-0.9.5-material-types",
                )
            )
    names = {name.casefold(): name for name in DEFAULT_NAMES}
    for table in (templates, products):
        for name in connection.scalars(sa.select(table.c.material_type).order_by(table.c.material_type)):
            names.setdefault(name.casefold(), name)
    connection.execute(
        catalog.insert(),
        [{"id": uuid4(), "name": name, "name_key": key, "record_version": 1} for key, name in names.items()],
    )
    if changed:
        for job_type in ("spoolman.reconcile.full", "google.publish.pending"):
            connection.execute(
                outbox.insert().values(
                    id=uuid4(),
                    job_type=job_type,
                    idempotency_key="upgrade-0.9.5-material-types",
                    aggregate_type="system",
                    aggregate_id=uuid4(),
                    aggregate_version=1,
                    payload={},
                    status="PENDING",
                    attempts=0,
                    max_attempts=12,
                    next_attempt_at=now,
                    created_at=now,
                )
            )
    # Existing agent heartbeat comparison queues the renamed desired library,
    # including for offline workstations when they next connect. No file is
    # touched during migration and the closed-Cura guard remains authoritative.


def downgrade() -> None:
    """Preserve corrected live labels; refuse to discard operator-managed choices."""
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events WHERE action IN ('material_type.create', 'material_type.rename'))"
        )
    ):
        raise RuntimeError("Operator-managed material types exist; restore a pre-upgrade backup")
    op.drop_table("material_types")
