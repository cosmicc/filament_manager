# 17 - Docker Compose and Swarm Deployment

## Production standard

Production uses two stack files:

- `examples/spoolman-stack.yml`
- `examples/filament-manager-stack.yml`

The central PostgreSQL server is outside both stacks. A shared external overlay network connects the applications.

The examples publish Spoolman on `7912` and Filament Manager on `8080`. An existing authenticated reverse-proxy overlay may be added to either stack after replacing the example network and hostnames with the local environment.

## One-time prerequisites

```bash
docker network create --driver overlay --attachable filament-services
```

Create or designate an external volume for Spoolman's local data directory:

```bash
docker volume create spoolman_data
```

For a multi-node Swarm, configure that external volume using the existing shared/NFS storage policy or constrain the service to the node that owns the volume. A local-driver external volume must exist on the constrained node, not only on the Swarm manager.

## Deployment order

1. Provision both PostgreSQL databases and roles.
2. Create `filament-services`.
3. Create `spoolman_db_password`.
4. Deploy Spoolman:

```bash
docker stack deploy -c spoolman-stack.yml spoolman
```

5. Verify `spoolman_spoolman` and its published endpoint.
6. Create Filament Manager secrets.
7. Deploy Filament Manager:

```bash
docker stack deploy -c filament-manager-stack.yml filament-manager
```

8. Verify cross-stack API connectivity from Filament Manager to `http://spoolman_spoolman:8000`.

## Independent lifecycle

```bash
# Upgrade or roll back Spoolman only
docker stack deploy -c spoolman-stack.yml spoolman

# Upgrade or roll back Filament Manager only
docker stack deploy -c filament-manager-stack.yml filament-manager
```

Do not combine the stacks for production convenience. Independent deployment is a reliability requirement.

## Service discovery

Swarm prefixes service DNS names with the stack name. With the examples:

- stack: `spoolman`
- service: `spoolman`
- DNS: `spoolman_spoolman`

Both services must join the same external network. Internal service names are not accessible from Moonraker outside Swarm.

## Image policy

- Pin tested immutable version tags or digests.
- Do not use `latest` in production.
- Upgrade Spoolman separately after reviewing upstream migrations and release notes.
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

`examples/docker-compose.yml` runs both applications in one Compose project for development and integration tests and mounts `examples/config.local.yaml`, where Spoolman resolves as `http://spoolman:8000`. It is not the recommended production layout.

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
