"""Move compatibility from sides to whole plates; conflicting sides become unrated.

Revision ID: fb123c4d5e67
Revises: fa012b3c4d56
"""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "fb123c4d5e67"
down_revision = "fa012b3c4d56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep equal/single ratings, reset disagreements as explicitly approved."""
    connection = op.get_bind()
    metadata = sa.MetaData()
    settings = sa.Table("application_settings", metadata, autoload_with=connection)
    sides = sa.Table("build_plate_surfaces", metadata, autoload_with=connection)
    audits = sa.Table("audit_events", metadata, autoload_with=connection)
    mapping = {
        str(side): str(plate)
        for side, plate in connection.execute(sa.select(sides.c.id, sides.c.build_plate_id))
    }
    for row in connection.execute(
        sa.select(settings).where(settings.c.key.startswith("plate_ratings.", autoescape=True))
    ).mappings():
        before = row["value"]
        grouped: dict[str, set[int]] = {}
        for side, stars in before.items() if isinstance(before, dict) else []:
            if side in mapping and type(stars) is int and 0 <= stars <= 5:
                grouped.setdefault(mapping[side], set()).add(stars)
        after = {plate: next(iter(stars)) for plate, stars in grouped.items() if len(stars) == 1}
        now = datetime.now(UTC)
        connection.execute(
            settings.update()
            .where(settings.c.id == row["id"])
            .values(value=after, record_version=row["record_version"] + 1, updated_at=now)
        )
        connection.execute(
            audits.insert().values(
                id=uuid4(),
                actor_id=None,
                source="migration",
                action="template.plate_ratings.whole_plate",
                object_type="application_setting",
                object_id=row["id"],
                before=before,
                after=after,
                metadata={
                    "conflicting_plates_reset": sorted(
                        plate for plate, stars in grouped.items() if len(stars) > 1
                    )
                },
                occurred_at=now,
                correlation_id="upgrade-0.8.4-plate-ratings",
            )
        )
    # Publication's periodic full-content digest notices the changed business map.
    # Historical print evidence and the original maps retained in audit are immutable.


def downgrade() -> None:
    """Expand ratings to both sides; refuse to silently discard custom ownership."""
    connection = op.get_bind()
    metadata = sa.MetaData()
    settings = sa.Table("application_settings", metadata, autoload_with=connection)
    sides = sa.Table("build_plate_surfaces", metadata, autoload_with=connection)
    if connection.scalar(
        sa.select(settings.c.id)
        .where(settings.c.key.startswith("filament_plate_ratings.", autoescape=True), settings.c.value != {})
        .limit(1)
    ):
        raise RuntimeError("Remove filament build-plate overrides before downgrading; retain a backup.")
    mapping: dict[str, list[str]] = {}
    for side, plate in connection.execute(sa.select(sides.c.id, sides.c.build_plate_id)):
        mapping.setdefault(str(plate), []).append(str(side))
    for row in connection.execute(
        sa.select(settings).where(settings.c.key.startswith("plate_ratings.", autoescape=True))
    ).mappings():
        value = {side: stars for plate, stars in row["value"].items() for side in mapping.get(plate, [])}
        connection.execute(
            settings.update()
            .where(settings.c.id == row["id"])
            .values(value=value, record_version=row["record_version"] + 1)
        )
