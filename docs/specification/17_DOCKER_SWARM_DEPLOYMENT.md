# 17 - Docker Compose and Swarm Deployment

## Production standard

The repository root `docker-stack.yml` deploys three services:

- `spoolman`;
- Filament Manager `web`;
- Filament Manager `worker`.

PostgreSQL is always remote. The `filament_manager` and `spoolman` databases have different owners and credentials even when hosted by the same PostgreSQL server. The stack publishes Spoolman on `7912` and Filament Manager on `8080` by default.

## One-time prerequisites

1. Provision the remote databases and roles with `docker/provision-databases.sql`.
2. Restrict PostgreSQL network access to approved Swarm nodes and require encrypted connections.
3. Populate all Filament Manager, Spoolman, one-printer Moonraker, Google, database, and tuning variables in a protected, ignored `.env` or Portainer variable set.
4. Pin immutable application images and export the variables from `.env`.

No Filament Manager Docker config or Docker secret object is required. Fixed application invariants remain code defaults; all deployment-specific values are stack variables.

The stack creates its overlay and volumes. For a multi-node Swarm, use shared storage or placement constraints so `filament_manager_data` and `spoolman_data` cannot be rescheduled onto empty local volumes.

## Deployment order

1. Run the Filament Manager Alembic migration as a one-shot Swarm job.
2. Confirm that the migration completed successfully and remove the completed job.
3. Validate the interpolated stack with `docker stack config`.
4. Deploy `docker-stack.yml` as stack `filament-manager`.
5. Seed the configured printer and P1-P5 once.
6. Create the first Administrator through a short-lived bootstrap job.
7. Verify all health endpoints, service logs, and remote database connections.

Exact commands and environment-variable handling requirements are in `INSTALL.md`.

## Service discovery

Within the combined stack, Filament Manager connects to `http://spoolman:8000` on the stack overlay. This internal name is not accessible from Moonraker outside Swarm; Moonraker uses the stable published LAN hostname and port.

## Independent-stack alternative

`docker/spoolman-stack.yml` and `docker/filament-manager-stack.yml` retain independent application rollout and rollback boundaries. They require a pre-created external `filament-services` network and use the stack-prefixed Spoolman DNS name `spoolman_spoolman`.

## Image policy

- Pin tested immutable version tags or digests.
- Do not use `latest` in production.
- Change the Spoolman image independently only after reviewing upstream migrations and release notes.
- Run one Spoolman replica with `stop-first` update order.
- Use `start-first` for Filament Manager only when migrations and worker leases make concurrent versions safe.

## Health and observability

Spoolman:

- `/api/v1/health`
- container and service logs
- database connection health
- API latency and WebSocket reconnects
- optional Prometheus metrics

Filament Manager:

- `/health/live`
- `/health/ready`
- `/metrics`
- outbox depth and retry count
- Spoolman reconciliation lag
- Google publication lag

## Local development

`docker/docker-compose.yml` runs both applications and a local PostgreSQL container in one Compose project for development and integration tests. The production stack uses the remote database instead.

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
