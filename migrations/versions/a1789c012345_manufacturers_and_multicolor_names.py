"""Normalize manufacturer identities and retain ordered multicolor names.

Revision ID: a1789c012345
Revises: a0678b901234
"""

from datetime import UTC, datetime
from unicodedata import normalize
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a1789c012345"
down_revision = "a0678b901234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Combine brands only, preserving every product UUID and immutable snapshot."""

    op.add_column("filament_products", sa.Column("color_names", JSONB(), nullable=False, server_default="[]"))
    connection = op.get_bind()
    metadata = sa.MetaData()
    vendors, products, colors, audit, jobs = [
        sa.Table(name, metadata, autoload_with=connection)
        for name in ("vendors", "filament_products", "filament_colors", "audit_events", "outbox_jobs")
    ]
    now = datetime.now(UTC)

    def record(action: str, kind: str, row: dict, after: dict) -> None:
        """Retain original identity metadata for operational review."""
        connection.execute(
            audit.insert().values(
                id=uuid4(),
                source="migration",
                action=action,
                object_type=kind,
                object_id=row["id"],
                before={key: row[key] for key in ("name", "aliases", "notes", "preferred") if key in row},
                after=after,
                metadata={},
                correlation_id=revision,
                occurred_at=now,
            )
        )

    groups: dict[str, list] = {}
    for row in connection.execute(sa.select(vendors).order_by(vendors.c.created_at, vendors.c.id)).mappings():
        name = normalize("NFKC", row["name"]).strip().upper()
        if not 1 <= len(name) <= 160 or any(not c.isprintable() for c in name):
            raise RuntimeError(
                "Manufacturer normalization requires a bounded printable name; correct catalog before upgrading"
            )
        groups.setdefault(name, []).append(row)
    for name, group in groups.items():
        target = next((row for row in group if row["name"] == name), group[0])
        aliases = list(
            dict.fromkeys(value for row in group for value in [row["name"], *(row["aliases"] or [])])
        )
        notes = "\n\n".join(dict.fromkeys(row["notes"] for row in group if row["notes"])) or None
        for row in group:
            if row["id"] == target["id"]:
                continue
            connection.execute(
                products.update()
                .where(products.c.vendor_id == row["id"])
                .values(
                    vendor_id=target["id"],
                    record_version=products.c.record_version + 1,
                    updated_at=now,
                )
            )
            record("vendor.uppercase_merge", "vendor", row, {"merged_into": str(target["id"]), "name": name})
            connection.execute(vendors.delete().where(vendors.c.id == row["id"]))
        if target["name"] != name or len(group) > 1:
            record("vendor.uppercase", "vendor", target, {"name": name})
            connection.execute(
                vendors.update()
                .where(vendors.c.id == target["id"])
                .values(
                    name=name,
                    aliases=aliases,
                    notes=notes,
                    preferred=any(row["preferred"] for row in group),
                    record_version=target["record_version"] + 1,
                    updated_at=now,
                )
            )
    samples: dict[str, str] = {}
    for row in connection.execute(
        sa.select(colors).where(colors.c.color_mode == "solid").order_by(colors.c.normalized_name)
    ).mappings():
        samples.setdefault(row["color_hex"].upper(), row["name"])
    for row in connection.execute(
        sa.select(products).where(products.c.color_mode == "multicolor")
    ).mappings():
        names = [samples.get(value.upper(), f"#{value.upper()}") for value in row["color_hexes"]]
        connection.execute(
            audit.insert().values(
                id=uuid4(),
                source="migration",
                action="filament.multicolor_names",
                object_type="filament_product",
                object_id=row["id"],
                before={"color_name": row["color_name"], "color_hexes": row["color_hexes"]},
                after={"color_name": "Multicolor", "color_names": names},
                metadata={},
                correlation_id=revision,
                occurred_at=now,
            )
        )
        connection.execute(
            products.update()
            .where(products.c.id == row["id"])
            .values(
                color_names=names,
                color_name="Multicolor",
                record_version=row["record_version"] + 1,
                updated_at=now,
            )
        )
    connection.execute(
        jobs.insert().values(
            id=uuid4(),
            job_type="spoolman.reconcile.full",
            idempotency_key=f"{revision}:metadata:{uuid4()}",
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


def downgrade() -> None:
    """Refuse to discard component identities; restore a backup for full reversal."""

    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM filament_products WHERE color_names <> '[]'::jsonb)")
    ):
        raise RuntimeError("Cannot discard multicolor names; restore a pre-upgrade backup")
    op.drop_column("filament_products", "color_names")
