"""Normalize legacy finishes and forget unused inventory choices.

Revision ID: f4a5b6c7d890
Revises: e3f4a5b6c789
Create Date: 2026-09-05
"""

from datetime import UTC, datetime
from unicodedata import normalize
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "f4a5b6c7d890"
down_revision = "e3f4a5b6c789"
branch_labels = None
depends_on = None


def _key(value: str | None) -> str:
    """Use the same bounded-name identity as the application."""

    return normalize("NFKC", value or "").strip().casefold()


def upgrade() -> None:
    """Correct live metadata only; never rewrite retained print/profile snapshots."""

    connection = op.get_bind()
    metadata = sa.MetaData()
    products, colors, choices, audit, jobs = [
        sa.Table(name, metadata, autoload_with=connection)
        for name in (
            "filament_products",
            "filament_colors",
            "filament_attribute_choices",
            "audit_events",
            "outbox_jobs",
        )
    ]
    now = datetime.now(UTC)
    used_colors: set[str] = set()
    used_attributes: set[tuple[str, str]] = set()
    for product in connection.execute(sa.select(products)).mappings():
        used_colors.add(_key(product["color_name"]))
        changes = {}
        if _key(product["finish"]) in ("", "none"):
            changes["finish"] = "Standard"
        if not _key(product["filler"]):
            changes["filler"] = "None"
        for kind in ("filler", "finish"):
            used_attributes.add((kind, _key(changes.get(kind, product[kind]))))
        if not changes:
            continue
        version = product["record_version"] + 1
        connection.execute(
            products.update()
            .where(products.c.id == product["id"])
            .values(
                **changes,
                record_version=version,
                updated_at=now,
            )
        )
        connection.execute(
            audit.insert().values(
                id=uuid4(),
                source="migration",
                action="filament.choice_normalization",
                object_type="filament_product",
                object_id=product["id"],
                before={key: product[key] for key in changes},
                after=changes,
                metadata={},
                correlation_id=revision,
                occurred_at=now,
            )
        )
        connection.execute(
            jobs.insert().values(
                id=uuid4(),
                job_type="spoolman.filament.upsert",
                idempotency_key=f"choice-normalization:{product['id']}:{revision}",
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
    # Delete exact metadata IDs only. Archived products participate above.
    for color in connection.execute(sa.select(colors)).mappings():
        if _key(color["normalized_name"]) not in used_colors:
            connection.execute(colors.delete().where(colors.c.id == color["id"]))
    for choice in connection.execute(sa.select(choices)).mappings():
        if (choice["kind"], _key(choice["name"])) not in used_attributes:
            connection.execute(choices.delete().where(choices.c.id == choice["id"]))


def downgrade() -> None:
    """Keep corrected values; discarded unused choices require a backup to recover."""
