"""Consolidate unspecified manufacturers without rewriting historical snapshots.

Revision ID: c7d8e9f012a3
Revises: b6c7d8e9f012
"""

from datetime import UTC, datetime
from unicodedata import normalize
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "c7d8e9f012a3"
down_revision = "b6c7d8e9f012"
branch_labels = None
depends_on = None

IDENTITY_COLUMNS = ["vendor_id", "material_type", "product_name", "color_name", "diameter_mm"]


def upgrade() -> None:
    """Merge only placeholder identities, including archived and missing assignments."""

    connection = op.get_bind()
    # Product UUIDs, not legacy labels, identify independent inventory records.
    # Retain the lookup index without preventing placeholder consolidation.
    op.drop_constraint("uq_filament_product_identity", "filament_products", type_="unique")
    op.create_index("ix_filament_product_identity", "filament_products", IDENTITY_COLUMNS)
    metadata = sa.MetaData()
    vendors, products, audit, jobs = [
        sa.Table(name, metadata, autoload_with=connection)
        for name in ("vendors", "filament_products", "audit_events", "outbox_jobs")
    ]
    placeholders = [
        row
        for row in connection.execute(sa.select(vendors)).mappings()
        if normalize("NFKC", row["name"]).strip().casefold()
        in {"unknown", "unspecified", "unspecified manufacturer", "unspecified vendor"}
    ]
    target = next((row for row in placeholders if row["name"] == "Unknown"), None)
    unknown_id = target["id"] if target else uuid4()
    now = datetime.now(UTC)
    if target is None:
        connection.execute(
            vendors.insert().values(
                id=unknown_id,
                name="Unknown",
                preferred=False,
                aliases=[],
                record_version=1,
                created_at=now,
                updated_at=now,
            )
        )
    old_ids = [row["id"] for row in placeholders if row["id"] != unknown_id]
    candidates = list(
        connection.execute(
            sa.select(products).where(
                sa.or_(products.c.vendor_id.is_(None), products.c.vendor_id.in_([unknown_id, *old_ids]))
            )
        ).mappings()
    )
    for row in candidates:
        if row["vendor_id"] == unknown_id:
            continue
        connection.execute(
            products.update()
            .where(products.c.id == row["id"])
            .values(
                vendor_id=unknown_id,
                record_version=row["record_version"] + 1,
                updated_at=now,
            )
        )
        connection.execute(
            audit.insert().values(
                id=uuid4(),
                source="migration",
                action="filament.manufacturer_normalization",
                object_type="filament_product",
                object_id=row["id"],
                before={"vendor_id": str(row["vendor_id"]) if row["vendor_id"] else None},
                after={"vendor_id": str(unknown_id)},
                metadata={},
                correlation_id=revision,
                occurred_at=now,
            )
        )
    if old_ids:
        for old in placeholders:
            if old["id"] == unknown_id:
                continue
            connection.execute(
                audit.insert().values(
                    id=uuid4(),
                    source="migration",
                    action="vendor.placeholder_consolidation",
                    object_type="vendor",
                    object_id=old["id"],
                    before={key: old[key] for key in ("name", "aliases", "notes", "preferred")},
                    after={"merged_into": str(unknown_id)},
                    metadata={},
                    correlation_id=revision,
                    occurred_at=now,
                )
            )
        connection.execute(vendors.delete().where(vendors.c.id.in_(old_ids)))
    # Full metadata convergence also updates linked spool labels and shared tares;
    # periodic Cura convergence regenerates live metadata, never historical records.
    connection.execute(
        jobs.insert().values(
            id=uuid4(),
            job_type="spoolman.reconcile.full",
            idempotency_key=f"{revision}:defaults:{uuid4()}",
            aggregate_type="vendor",
            aggregate_id=unknown_id,
            aggregate_version=1,
            payload={},
            status="PENDING",
            attempts=0,
            max_attempts=12,
            next_attempt_at=now,
            created_at=now,
        )
    )


def downgrade() -> None:
    """Restore the old schema only when safe; retain normalized manufacturer data."""

    connection = op.get_bind()
    # Serialize the preflight with writes until the unique constraint is restored.
    connection.execute(sa.text("LOCK TABLE filament_products IN ACCESS EXCLUSIVE MODE"))
    products = sa.Table("filament_products", sa.MetaData(), autoload_with=connection)
    columns = [products.c[name] for name in IDENTITY_COLUMNS]
    collision = connection.execute(
        sa.select(sa.literal(1))
        .select_from(products)
        .where(*(column.is_not(None) for column in columns))
        .group_by(*columns)
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    if collision:
        raise RuntimeError(
            "Cannot restore the legacy filament identity rule while duplicate records exist. "
            "Keep the current schema or restore a pre-upgrade backup; no inventory was changed."
        )
    op.create_unique_constraint("uq_filament_product_identity", "filament_products", IDENTITY_COLUMNS)
    op.drop_index("ix_filament_product_identity", table_name="filament_products")
