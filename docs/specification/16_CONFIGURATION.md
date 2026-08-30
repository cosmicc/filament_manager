# 16 - Configuration

## Configuration ownership

Filament Manager and Spoolman use separate configuration and credential sets even when they run in one production stack.

### Filament Manager configuration

Docker builds the complete validated runtime configuration directly from scoped environment variables. No application Docker config is created or mounted. The environment contract includes:

- canonical PostgreSQL connection assembled from scoped stack variables
- Spoolman API base URL
- one Moonraker printer's identifier, display name, HTTP URL, optional WebSocket URL and API key, and nozzle diameter
- Google publication
- optional Bugsnag error reporting, release stage, and browser performance monitoring
- synchronization policies
- bounded browser-session absolute and idle lifetimes, defaulting to thirty days and seven days
- build plates
- future hardware adapters

### Spoolman configuration

Stored directly in `docker-stack.yml` as scoped environment values, including `SPOOLMAN_DB_PASSWORD`.

## Filament Manager Spoolman URL

Default combined-stack variable:

```text
SPOOLMAN_INTERNAL_URL=http://spoolman:8000
```

This uses the `spoolman` service alias on the combined stack overlay. The optional separate-stack configuration uses `http://spoolman_spoolman:8000`.

## Credential separation

Filament Manager service credential variables:

- `FILAMENT_MANAGER_DATABASE_URL`, assembled inside the stack from `FILAMENT_MANAGER_DB_*` and `POSTGRES_*`
- `FILAMENT_MANAGER_GOOGLE_SERVICE_ACCOUNT_JSON`
- `FILAMENT_MANAGER_MOONRAKER_API_KEY`
- `FILAMENT_MANAGER_BUGSNAG_API_KEY` when optional monitoring is enabled

Spoolman service credential variable:

- `SPOOLMAN_DB_PASSWORD`

Never pass `SPOOLMAN_DB_PASSWORD` into Filament Manager. Never pass `FILAMENT_MANAGER_DATABASE_URL` or `FILAMENT_MANAGER_DB_PASSWORD` into Spoolman.

## Deployment parameters

Copy `.env.example` to the ignored `.env`, protect it with mode `0600`, and populate both ordinary settings and credentials. Export it explicitly before command-line deployment because `docker stack deploy` does not load `.env` automatically. This environment-variable delivery is transitional: authorized Docker and Portainer operators can inspect service values, so keep access narrow and never print rendered stack specifications into logs.

`docker-stack.yml` requires the public Filament Manager URL, public Spoolman URL, one Moonraker printer name and HTTP URL, its nozzle diameter, PostgreSQL routing, and credentials. The database defaults are `filament_user`, `spoolman_user`, `FILAMENT_MANAGER_DB_SSLMODE=disable`, and `SPOOLMAN_DB_QUERY=ssl=disable`. Empty `MOONRAKER_WEBSOCKET_URL` derives the conventional endpoint from `MOONRAKER_BASE_URL`. Operational values documented with defaults remain overrideable variables.

## Configuration validation

At startup, Filament Manager must verify:

- database connection and schema version
- Spoolman URL syntax and API health
- no Spoolman database credential is present in Filament Manager config
- Moonraker URLs
- exactly one environment-configured Moonraker printer
- Google Sheet and service-account configuration
- Bugsnag enabled/performance dependencies and 32-character hexadecimal SDK-key format
- valid plate codes and mesh names

## Local development

The combined `docker/docker-compose.yml` runs a local PostgreSQL container in addition to Filament Manager and Spoolman. Production `docker-stack.yml` never installs PostgreSQL and always uses the configured remote server.

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
