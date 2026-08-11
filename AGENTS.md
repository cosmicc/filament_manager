# Filament Manager Agent Guide

## Mission

Build and maintain Filament Manager, a security-focused, self-hosted application for filament inventory, measurements, material profiles, calibration, build plates, and supported Klipper ecosystem integration.

The product name is **Filament Manager**. Do not introduce the former project name in code, documentation, configuration, deployment objects, or user-facing copy.

## Authority and boundaries

1. The `filament_manager` PostgreSQL database is canonical.
2. Standalone Spoolman is the printer-facing operational projection and usage service.
3. Google Sheets is a one-way, read-only publication target.
4. The supplied workbook is an initial-import fixture only.
5. Filament Manager integrates with Spoolman through its supported REST API and periodic reconciliation; direct database access is prohibited.
6. The default production deployment uses the root `docker-stack.yml` to run Spoolman and Filament Manager together while keeping their remote PostgreSQL databases, roles, credentials, migrations, and backups separate. The independent stack files under `docker/` remain available when operational isolation is required.
7. Cura files are changed only by the outbound-only per-user workstation agent under `workstation-agent/`; the server never reaches into a workstation or listens on an agent port.
8. Docker deployments are environment-only: every deployer-supplied application setting and credential comes from scoped stack variables, with no mounted application Docker config and no Docker secrets. The current variable contract supports exactly one Moonraker printer. Treat credential variables as a transitional risk, restrict manager and Portainer access, keep populated `.env` files untracked with mode `0600`, and never log or render these values.
9. Successful CI for a `main` push publishes the Filament Manager container for AMD64 and ARM64 with `latest` and immutable `sha-<commit>` tags. Treat `latest` as a testing convenience; production deployments pin an immutable SHA tag or digest. Image publication does not authorize a Git tag or GitHub Release.

## Required stack

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL, and psycopg 3
- React, TypeScript, and Vite
- PostgreSQL-backed jobs using transactional outbox, `FOR UPDATE SKIP LOCKED`, and advisory locks
- Pytest, Ruff, mypy, Vitest, and Playwright
- Structured JSON logging, Prometheus metrics, multi-stage Docker builds, and separate Swarm stack files

Do not add Redis, Celery, Kafka, or another message broker without an approved architecture decision.

## Agent routing

- [Database and migrations](skills/database.md)
- [Security and local-role authentication](skills/security.md)
- [Frontend design and accessibility](skills/frontend.md)
- [Testing and validation](skills/testing.md)
- [Docker, Swarm, and operations](skills/deployment.md)

Read the relevant skill before changing that area. The numbered source specifications are under `docs/specification/`.

## Visual contract

Use the approved Workshop Navy design system in [docs/design/palette.png](docs/design/palette.png), including its paired light and dark modes. The implementation references are under `docs/design/concepts/`. Keep spacing uniform and preserve the table-driven and workflow-driven layouts shown there.

## Core implementation rules

- UUID technical keys, immutable human spool IDs, integer record versions, UTC storage, and America/Detroit display.
- PostgreSQL `NUMERIC`, never binary floating point, for mass, density, dimensions, calibrated factors, and money.
- Immutable measurement, usage, audit, and calibration-result history.
- Optimistic concurrency for mutable resources and idempotency keys for external writes and device events.
- Every canonical mutation records an audit event and creates external projection jobs in the same transaction when required.
- Preserve unknown Spoolman `extra` fields.
- Google or Spoolman outages must queue work and must not corrupt canonical state.
- Workers coordinate periodic Spoolman reconciliation and Google publication with PostgreSQL advisory locks.
- NFC UIDs are identifiers, not credentials. Scale readings remain telemetry until stability and identity checks pass.
- Workstation pairing codes are single-use and short-lived; agent bearer credentials are hashed, revocable, scoped only to agent endpoints, and never logged.
- Cura deployments must wait for Cura to close, match exactly one machine/nozzle, back up affected files, use atomic replacement, and preserve unmanaged profiles and unknown inherited start G-code.
- Preserve build-plate identifiers `P1` through `P5` exactly.
- Published material profiles are immutable; revisions create new versions.

## Documentation and release discipline

Keep `README.md`, `CHANGELOG.md`, `USER_CHANGELOG.md`, `VERSION`, this file, and affected skill files synchronized with meaningful changes. Changelog versions use `MM.DD.YYYY` dates and always contain Added, Changed, and Fixed sections.

Do not commit, push, tag, publish images, or create a release unless the user explicitly authorizes that boundary.
