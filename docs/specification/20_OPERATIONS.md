# 20 - Operations Runbook

## Routine checks

### Spoolman service

```bash
docker stack services filament-manager
docker service ps filament-manager_spoolman
docker service logs --since 30m filament-manager_spoolman
```

Check:

- API health
- central PostgreSQL connectivity
- published port `7912`
- Moonraker connection status
- disk/log volume availability
- image version and pending upstream release review

### Filament Manager services

```bash
docker stack services filament-manager
docker service ps filament-manager_web
docker service logs --since 30m filament-manager_web
docker service logs --since 30m filament-manager_worker
```

Check:

- canonical database connectivity
- Spoolman reconciliation lag
- outbox queue depth
- Google publication status
- Moonraker reachability

Canonical mutations normally begin Spoolman projection within one worker polling cycle. The default one-minute full sweep imports usage before repairing every canonical vendor, filament, and spool. Confirm the Spoolman integration card reports both API and managed-field readiness, and confirm recent `spoolman.reconcile.full` jobs complete.

## Upgrade Spoolman

1. Review upstream release notes and migration warnings.
2. Confirm backup coverage of the `spoolman` database.
3. Pin the new tested Spoolman image in the exported stack variables.
4. Redeploy `docker-stack.yml` without changing the Filament Manager image.
5. Verify API health and Moonraker/Fluidd behavior.
6. Verify Filament Manager WebSocket reconnection and reconciliation.
7. Roll back the image and restore the database only if the upstream migration is not backward compatible.

## Upgrade Filament Manager

1. Back up `filament_manager`.
2. Run or verify migrations.
3. Redeploy `docker-stack.yml` with the new Filament Manager image and the existing Spoolman image.
4. Confirm Spoolman remained available throughout.
5. Check outbox and reconciliation backlog.

## Outage procedures

### Filament Manager unavailable

- Leave Spoolman and Moonraker running.
- Continue printing and collecting usage in Spoolman.
- Restore Filament Manager, then run inbound reconciliation.

### Spoolman unavailable

- Do not directly update its database.
- Restore the Spoolman service or database connectivity.
- Allow Filament Manager projection jobs to remain queued.
- Confirm Moonraker reconnects and reconcile missed usage.

### Stack overlay missing

```bash
docker stack deploy -c docker-stack.yml filament-manager
```

The combined stack recreates its missing overlay. Verify internal DNS and API health after its services reattach. For the optional independent-stack layout, recreate the external overlay and redeploy both stacks.

### Central PostgreSQL unavailable

Treat each database independently during diagnosis. Do not broaden grants or reuse the other application's credentials as a shortcut.

## Backup checks

- both databases included in backup sets
- last successful backup and WAL archive time
- periodic isolated restore
- configuration and private stack-variable inventory current
- Google Sheet not counted as backup

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
