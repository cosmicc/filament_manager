# 26 - Backup, Recovery, and Data Retention

## Backup set

- canonical `filament_manager` PostgreSQL database
- distinct Spoolman `spoolman` PostgreSQL database
- both production stack files
- encrypted stack-variable backup according to operations policy
- Spoolman local data directory where operationally required
- Google Sheet ID and template metadata
- label and Cura export templates
- sanitized versioned Cura recovery snapshots stored in canonical PostgreSQL

## Independent restore objectives

The stack boundary requires two restoration paths:

### Filament Manager restore

Restore the canonical database, migrations, stack, and protected variable inventory. Spoolman may remain online while this occurs. After recovery, reconcile usage accumulated during the outage.

Retained Cura recovery points return with the canonical database. They remain bound to their originating paired workstation and exact Cura version. Re-pairing a replacement workstation does not silently transfer that trust boundary.

### Spoolman restore

Restore the Spoolman database and stack independently. If the database cannot be restored, initialize a blank database, reproject canonical records through the API, and reconcile printer-originated state.

## Application snapshot scheduling

The runtime image uses PostgreSQL client 18 so `pg_dump` can read PostgreSQL 18 and older supported server versions. Scheduled and Administrator-requested dumps are deferred while a canonical print is in progress so they do not compete with Klipper host timing. A failed automatic dump records a bounded failure state and a persisted exponential retry deadline beginning at fifteen minutes and capped at six hours; the one-minute scheduler must not spawn the failed operation on every pass. PostgreSQL stderr is bounded and classified into safe operator guidance without exposing database identifiers or connection details.

## Retention

- audit and measurement history: retain indefinitely unless policy changes
- device raw telemetry: short configurable retention, summarized afterward
- completed outbox jobs: retain for troubleshooting, then archive
- calibration artifacts: retain with profile versions
- Spoolman logs: retain according to centralized logging policy
- sanitized Cura recovery snapshots: newest fifteen distinct automatic points per workstation installation and Cura version, plus named points retained until explicit deletion
- workstation-local pre-restore archives: retain according to workstation privacy/storage policy and remove deliberately when no longer required

## Quarterly recovery test

1. restore `filament_manager` to an isolated environment;
2. restore or initialize `spoolman` separately;
3. deploy both services on an isolated combined-stack overlay;
4. rebuild Spoolman projections through the API;
5. create a new Google publication workbook;
6. compare counts, weights, profile versions, plates, and calibration status;
7. simulate a Filament Manager outage while usage continues in Spoolman;
8. document recovery time and discrepancies.
9. verify retained Cura recovery metadata and exercise one exact-version workstation restore with non-production credentials.

## Application validation and derived-state rebuild

The Diagnostics page and `filament-manager-cli verify` run the same read-only recovery checks against schema revision, measurement integrity, credential hashes, Spoolman consistency, Google publication state, managed Cura synchronization state, and Cura recovery readiness. Results are bounded, sanitized, and persisted for operator review. These checks supplement but never replace an isolated PostgreSQL restore test or an exact-version workstation recovery exercise.

After a canonical restore or external projection loss, an Administrator may use Diagnostics or `filament-manager-cli rebuild-projections --confirm`. The operation queues idempotent Spoolman, Google, and managed Cura projection work from canonical data. It does not mutate canonical inventory/history and does not back up or restore either PostgreSQL database.

## RPO and RTO

Set explicit targets based on the central PostgreSQL backup platform. Both databases should receive WAL-aware protection where available, but their restore priorities may differ: printer usage continuity favors Spoolman availability, while full business-state integrity depends on Filament Manager.

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
