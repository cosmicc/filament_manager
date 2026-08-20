# 17 - Docker Compose and Swarm Deployment

## Production standard

The repository root `docker-stack.yml` deploys three services:

- `spoolman`;
- Filament Manager `web`;
- Filament Manager `worker`.

PostgreSQL is always remote. The `filament_manager` and `spoolman` databases have different owners and credentials even when hosted by the same PostgreSQL server. The stack publishes Spoolman on `7912` and Filament Manager on `8080` by default.

## One-time prerequisites

1. Provision the remote databases and roles with `docker/provision-databases.sql`.
2. Restrict PostgreSQL network access to approved Swarm nodes. Both clients explicitly disable TLS, so the database network must be dedicated and isolated from untrusted systems.
3. Populate all Filament Manager, Spoolman, one-printer Moonraker, Google, database, optional Bugsnag, and tuning variables in a protected, ignored `.env` or Portainer variable set.
4. Pin immutable application images and export the variables from `.env`.

No Filament Manager Docker config or Docker secret object is required. Fixed application invariants remain code defaults; all deployment-specific values are stack variables.

The stack creates its overlay and volumes. For a multi-node Swarm, use shared storage or placement constraints so `filament_manager_data` and `spoolman_data` cannot be rescheduled onto empty local volumes.

## Deployment order

1. Validate the interpolated stack with `docker stack config`.
2. Deploy `docker-stack.yml` as stack `filament-manager`.
3. Web and worker entry points each request the stable PostgreSQL advisory lock, apply `alembic upgrade head`, and start only after success.
4. Confirm both service logs report migration completion; keep the documented one-shot migration only for stopped-service recovery.
5. Seed the configured printer and initial physical P1-P5 plates with Side A once.
6. Sign in with the automatically created first-install `admin` / `admin` account and complete the mandatory password change. An existing single account is retained during upgrade.
7. Install the Klipper plate-side macro; the worker automatically discovers later exact `P<number>` or `P<number>b` meshes and current active state.
8. Verify all health endpoints, service logs, and remote database connections.
9. Confirm Spoolman's managed projection fields are ready and a one-minute full convergence job projects existing canonical inventory.

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
- managed-field readiness and last successful full convergence
- active-spool and build-plate reconciliation freshness
- sanitized printer-information synchronization freshness
- Google publication lag
- optional sanitized Bugsnag error delivery and browser performance visibility

The image readiness probe connects to the web process over loopback and sends the hostname from `FILAMENT_MANAGER_BASE_URL`, preserving trusted-host validation. Worker and one-shot services must disable this web-only HTTP health check because they do not listen on port 8080.

Bugsnag remains default-off. When enabled, web and worker use the same SDK API key, the browser receives a minimal runtime configuration, and application availability never depends on successful delivery. The separate Upload API key is confined to authorized direct-push CI; hidden source maps are deleted before runtime assembly.

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
