# 04 - PostgreSQL Source of Truth

## Decision

The central PostgreSQL server is the highest-trust persistence platform. Filament Manager owns the canonical `filament_manager` database. The distinct Spoolman service uses a separate `spoolman` database on that same server.

## Required isolation

| Concern | Filament Manager | Spoolman |
|---|---|---|
| Database | `filament_manager` | `spoolman` |
| Owner/login | `filament_user` | `spoolman_user` |
| Schema migrations | Alembic in Filament Manager release | Upstream Spoolman release |
| Connection credential | Filament Manager services | Spoolman service |
| Backup object | Independent | Independent |
| Application integration | Canonical repository | REST/WebSocket API |

Rules:

- Never share a database role.
- Never put Filament Manager tables in the Spoolman database.
- Never grant Filament Manager direct read or write access to Spoolman tables.
- Never grant Spoolman access to Filament Manager tables.
- Restrict `pg_hba.conf` to approved Swarm node addresses and require SCRAM authentication.
- Explicitly disable PostgreSQL TLS only on the dedicated isolated database network; credentials and queries are otherwise exposed in transit.
- Keep monitoring and backup roles separate from application roles.

## Canonical authority

Filament Manager PostgreSQL owns:

- products, vendors, physical spool identity, and human spool codes
- measurements and correction history
- Cura profile versions and calibration results
- build plates and bed-mesh mappings
- audit, labels, synchronization state, and Google publication state

Spoolman owns its internal schema and is authoritative for printer-originated consumption events until Filament Manager records and acknowledges them through the supported API.

Spool locations are a narrow bootstrap exception: an existing non-empty Spoolman location may initialize a legacy canonical spool whose location has never been set. Filament Manager records that ownership transition and thereafter remains authoritative, projecting local edits and repairing remote location drift.

## PostgreSQL features used by Filament Manager

- `NUMERIC` for mass, density, money, and calibrated factors
- `JSONB` for extensible settings and audited changes
- `TIMESTAMPTZ` for timestamps
- partial and functional indexes
- advisory locks for singleton jobs
- `FOR UPDATE SKIP LOCKED` for worker queues
- transactional outbox insertion
- row-version fields for optimistic concurrency

## Migration ownership

Filament Manager web and worker container entry points automatically run Alembic before application startup while holding the stable application PostgreSQL advisory lock. A dedicated one-shot command is reserved for stopped-service recovery. Spoolman migrations are performed by the upstream Spoolman container against only the `spoolman` database.

## Backup policy

Back up both databases independently through the central PostgreSQL backup platform:

- include both databases in pgBackRest or equivalent coverage
- retain application and migration version metadata
- perform periodic restore tests
- treat Google Sheets as a view, not a backup
- treat Spoolman alone as incomplete because it does not contain profiles, plates, calibration sessions, or Filament Manager audit data

Filament Manager additionally creates logical snapshots of only its canonical database. The default policy runs every 24 hours and retains the newest ten automatic ZIPs. Each ZIP contains exactly `manifest.json` and a custom-format `database.dump`, with bounded metadata, sizes, and SHA-256 evidence. Manual/imported files do not consume automatic retention. Keep downloaded copies on protected storage outside the application host; an archive left only in the application volume does not protect against loss of that volume.

Imported archives require Administrator authorization and exact validation. They are trusted operator input, not a cross-database integration. Diagnostics stages an exact archive UUID after typed confirmation, but a dedicated maintenance process performs restoration only while web and worker are stopped. Restore suppresses ownership/ACL changes, uses one transaction, creates a safety snapshot first, applies forward Alembic migrations, and revokes restored browser sessions.

## Recovery priority

1. Restore `filament_manager`.
2. Restore `spoolman`, or initialize a blank Spoolman database.
3. Deploy the Spoolman service and verify health.
4. Reproject canonical inventory through the Spoolman API.
5. Reconcile printer-originated usage and align canonical active spool only after validating Moonraker against persisted physical Klipper state.
6. Rebuild the Google Sheet.

## Example provisioning

See:

- `docker/provision-databases.sql`
- the remote server's restricted `pg_hba.conf`

## Authoritative implementation references

- Spoolman repository: https://github.com/Donkie/Spoolman
- Spoolman Docker installation: https://github.com/Donkie/Spoolman/wiki/Installation
- Spoolman configuration variables: https://github.com/Donkie/Spoolman/blob/master/.env.example
- Spoolman security guidance: https://github.com/Donkie/Spoolman/wiki/Security
- Spoolman REST API: https://donkie.github.io/Spoolman/
- Moonraker Spoolman configuration: https://moonraker.readthedocs.io/en/stable/configuration/#spoolman
- Fluidd Spoolman support: https://docs.fluidd.xyz/features/spoolman
- Google Sheets API: https://developers.google.com/workspace/sheets/api
- Docker Swarm stack deployment: https://docs.docker.com/engine/swarm/stack-deploy/
- PostgreSQL documentation: https://www.postgresql.org/docs/
