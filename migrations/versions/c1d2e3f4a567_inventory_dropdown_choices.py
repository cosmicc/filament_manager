"""Remember filler/finish choices and default only blank canonical modifiers.

Revision ID: c1d2e3f4a567
Revises: b0c1d2e3f456
Create Date: 2026-09-05
"""

from datetime import UTC, datetime
from hashlib import sha256
from unicodedata import normalize
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c1d2e3f4a567"
down_revision = "b0c1d2e3f456"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Seed existing choices without touching retained print/profile snapshots."""

    op.create_table(
        "filament_attribute_choices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(96), nullable=False),
        sa.Column("name_key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("kind", "name_key", name="uq_filament_attribute_choice"),
        sa.CheckConstraint("kind IN ('filler', 'finish')", name="attribute_choice_kind"),
    )
    connection = op.get_bind()
    metadata = sa.MetaData()
    products = sa.Table("filament_products", metadata, autoload_with=connection)
    choices = sa.Table("filament_attribute_choices", metadata, autoload_with=connection)
    audit = sa.Table("audit_events", metadata, autoload_with=connection)
    jobs = sa.Table("outbox_jobs", metadata, autoload_with=connection)
    remembered = {("filler", "none"): "None", ("finish", "standard"): "Standard"}
    now = datetime.now(UTC)
    for product in connection.execute(sa.select(products).order_by(products.c.id)).mappings():
        changed = {}
        before = {}
        for kind, default in (("filler", "None"), ("finish", "Standard")):
            value = product[kind]
            if value is None or not value.strip():
                before[kind] = value
                changed[kind] = default
                value = default
            name = value.strip()
            remembered.setdefault((kind, normalize("NFKC", name).casefold()), name)
        if not changed:
            continue
        version = product["record_version"] + 1
        connection.execute(
            products.update()
            .where(products.c.id == product["id"])
            .values(
                **changed,
                record_version=version,
                updated_at=now,
            )
        )
        connection.execute(
            audit.insert().values(
                id=uuid4(),
                source="migration",
                action="filament.modifier_defaults",
                object_type="filament_product",
                object_id=product["id"],
                before=before,
                after=changed,
                metadata={},
                correlation_id=revision,
                occurred_at=now,
            )
        )
        connection.execute(
            jobs.insert().values(
                id=uuid4(),
                job_type="spoolman.filament.upsert",
                idempotency_key=f"modifier-defaults:{product['id']}:{revision}",
                aggregate_type="filament_product",
                aggregate_id=product["id"],
                aggregate_version=version,
                payload={"filament_product_id": str(product["id"])},
                status="PENDING",
                attempts=0,
                max_attempts=12,
                next_attempt_at=now,
                created_at=now,
            )
        )
    connection.execute(
        choices.insert(),
        [
            {
                "id": uuid4(),
                "kind": kind,
                "name": name,
                "name_key": sha256(normalized.encode("utf-8")).hexdigest(),
            }
            for (kind, normalized), name in remembered.items()
        ],
    )
    op.alter_column("filament_products", "filler", server_default="None")
    op.alter_column("filament_products", "finish", server_default="Standard")


def downgrade() -> None:
    """Remove the catalog; preserve valid backfilled names and their audit evidence."""

    op.alter_column("filament_products", "finish", server_default=None)
    op.alter_column("filament_products", "filler", server_default=None)
    op.drop_table("filament_attribute_choices")
