# 07 - Standalone Spoolman Integration

## Production decision

Spoolman is a **standalone Docker Swarm stack**, not a service inside the Filament Manager stack. It provides the established spool API, WebSocket events, labels and QR workflow, Moonraker integration, and Fluidd user experience.

## Rationale

- independent upgrades and rollbacks
- failure isolation from Filament Manager development
- continuous Moonraker usage reporting during Filament Manager restarts
- reuse by additional printers
- clear ownership of Spoolman migrations and runtime configuration

## Database

Spoolman uses its own `spoolman` PostgreSQL database and `spoolman_user` role on the central server. The password is a Docker secret mounted only into the Spoolman stack.

Filament Manager must never write directly to Spoolman tables. All reads and writes use the REST API or WebSocket interfaces.

## Ports and addresses

- Spoolman container port: TCP `8000`
- recommended published LAN port: TCP `7912`
- Filament Manager production URL with documented stack/service names: `http://spoolman_spoolman:8000`
- Moonraker URL: stable LAN DNS or IP, such as `http://spoolman.internal.example:7912`

The Swarm-internal service DNS name is not usable from the printer host.

## Shared overlay network

Create once:

```bash
docker network create --driver overlay --attachable filament-services
```

Declare `filament-services` as external in both stack files.

## Required environment variables

```yaml
environment:
  TZ: America/Detroit
  SPOOLMAN_HOST: 0.0.0.0
  SPOOLMAN_PORT: "8000"
  SPOOLMAN_DB_TYPE: postgres
  SPOOLMAN_DB_HOST: postgres.internal.example
  SPOOLMAN_DB_PORT: "5432"
  SPOOLMAN_DB_NAME: spoolman
  SPOOLMAN_DB_USERNAME: spoolman_user
  SPOOLMAN_DB_PASSWORD_FILE: /run/secrets/spoolman_db_password
```

Optional browser and security controls:

```yaml
  SPOOLMAN_CORS_ORIGIN: https://fluidd.internal.example
  SPOOLMAN_ALLOWED_HOSTS: spoolman.internal.example
```

`SPOOLMAN_CORS_ORIGIN` is for browser origins such as Fluidd hosted elsewhere. It is not required for Moonraker. Allowed hosts are hostnames without schemes or ports.

## Persistent directory

Mount `/home/app/.local/share/spoolman` even when PostgreSQL stores inventory. It retains logs and other application-local runtime files. In Swarm, use an external volume consistent with the existing shared-storage policy.

## Service policy

- one replica
- pin a tested image tag; do not use `latest` in production
- `stop-first` updates to avoid concurrent database migrations
- rollback on failed update
- API health check at `/api/v1/health`
- independent log collection and Prometheus scraping

## Object mapping

### Vendor

Manufacturer name and selected custom metadata.

### Filament

Material, vendor, product name/grade/hardness, diameter, density, nominal weight, color, temperatures, and compatible custom fields.

### Spool

Physical spool, initial weight, tare weight, remaining and used weight, price, first/last use, location, comment, and managed identifiers.

## Required custom fields

At minimum:

- `filament_manager_spool_uuid`
- `sheet_spool_id`
- `filler`
- `finish`
- `color_name`
- `profile_version`
- `preferred_plate`

## Extra-field safety

Spoolman API updates can replace an object's `extra` mapping. Read the current object, merge unknown keys, and send the merged result. Do not erase fields owned by another integration.

## Deployment example

Use `examples/spoolman-stack.yml`. Deploy it before the Filament Manager stack and verify the API from both a Swarm node and the printer network.

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
