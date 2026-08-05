# 16 - Configuration

## Configuration ownership

Filament Manager and Spoolman use separate configuration and secret sets because they are separate production stacks.

### Filament Manager configuration

Stored in `examples/config.yaml` and mounted into the Filament Manager stack. Key settings:

- canonical PostgreSQL connection secret
- Spoolman API base URL
- Moonraker printers
- Google publication
- synchronization policies
- build plates
- future hardware adapters

### Spoolman configuration

Stored directly in `examples/spoolman-stack.yml` as non-secret environment values plus the `spoolman_db_password` Docker secret.

## Filament Manager Spoolman URL

Default production example:

```yaml
spoolman:
  base_url: http://spoolman_spoolman:8000
```

This assumes stack name `spoolman`, service name `spoolman`, and both stacks attached to `filament-services`. The URL is configurable because stack names may differ.

## Secret separation

Filament Manager stack secrets:

- `filament_manager_database_url`
- `google_service_account`
- `moonraker_api_key`
- `application_secret`

Spoolman stack secrets:

- `spoolman_db_password`

Never mount `spoolman_db_password` into Filament Manager. Never mount `filament_manager_database_url` into Spoolman.

## Deployment parameters

Use `.env.example` only for non-secret hostnames, image tags, and public ports. Production passwords and tokens belong in Docker secrets.

## Configuration validation

At startup, Filament Manager must verify:

- database connection and schema version
- Spoolman URL syntax and API health
- no Spoolman database credential is present in Filament Manager config
- Moonraker URLs
- Google Sheet and service-account configuration
- valid plate codes and mesh names

## Development exception

The combined `docker-compose.yml` may run Filament Manager and Spoolman together for local testing. This does not change the production architecture decision.

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
