# 18 - Security Architecture

## Trust boundaries

- browser/user to Filament Manager
- Filament Manager to canonical PostgreSQL
- Filament Manager to standalone Spoolman API
- Spoolman to its PostgreSQL database
- Moonraker/Fluidd to Spoolman
- Filament Manager to Google APIs
- future scale/NFC devices to Filament Manager

## Database isolation

- separate databases and owners
- separate Docker secrets
- SCRAM authentication
- `pg_hba.conf` limited to Swarm node addresses
- no cross-database grants
- no direct Filament Manager queries against Spoolman tables
- distinct connection limits and monitoring labels

## Spoolman exposure

Spoolman has no built-in authentication. Therefore:

- do not expose port `7912` to the public internet
- allow only printer, management, and trusted LAN networks
- use authenticated reverse-proxy access for remote browser use
- set precise `SPOOLMAN_CORS_ORIGIN` values rather than `*`
- set `SPOOLMAN_ALLOWED_HOSTS` for real reverse-proxy hostnames
- do not rely on CORS as authentication

## Cross-stack network

`filament-services` is an internal integration network even though it is declared external to the stacks. Only services that need Spoolman integration should join it.

## Secrets

- use Docker secrets
- never commit credentials
- never put passwords directly in stack YAML
- rotate Spoolman and Filament Manager database credentials independently
- prevent secrets from appearing in logs, exceptions, metrics, or Google Sheet output

## API safety

- authenticate Filament Manager writes
- enforce role-based authorization
- use request IDs and audit logs
- validate all Spoolman payloads
- preserve unknown Spoolman `extra` fields
- protect against SSRF by allowing only configured Spoolman and Moonraker endpoints

## Future device security

- unique device credentials
- signed or authenticated events
- timestamp and replay-window validation
- rate limits
- NFC UIDs treated only as identifiers, never authenticators

## Backup security

Backups of both databases must use the central backup platform's encryption and retention controls. Restore tests must occur in isolated environments with non-production secrets.

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
