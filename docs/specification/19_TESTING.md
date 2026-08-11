# 19 - Testing Strategy

## Unit tests

- mass calculations and clamping
- density/length calculations
- profile validation
- calibration dependency invalidation
- plate/mesh validation
- Google output escaping
- idempotency-key generation
- Spoolman extra-field merge

## PostgreSQL integration tests

Use a real disposable PostgreSQL instance for:

- migrations
- numeric precision
- JSONB behavior
- advisory locks
- worker claiming with `SKIP LOCKED`
- outbox atomicity
- optimistic concurrency

## Connector tests

Mock or containerize:

- Spoolman REST and WebSocket
- Moonraker status and active-spool calls
- Google Sheets batch updates and quota failures

## End-to-end scenarios

1. Initial workbook import.
2. Manual weight entry updates canonical data, Spoolman, and Google.
3. Fluidd/Moonraker usage reduces remaining mass.
4. Spoolman offline and recovery with pending usage.
5. Google offline and later publication.
6. External Spoolman edit detected as drift.
7. Build plate `P3` selection loads mesh `P3`.
8. Calibration wizard publishes a new profile.
9. Repeating temperature step invalidates dependent results.
10. Scale replay and unstable sample rejection.
11. NFC unknown tag and confirmed activation.

## Swarm tests

- required stack variables reach only their intended services
- overlay DNS resolution
- published 7912 reaches Spoolman target 8000
- service restart does not duplicate jobs
- rolling update does not run conflicting migrations

## Restore test

Restore both PostgreSQL databases independently to an isolated environment, deploy both services in the combined stack, rebuild Spoolman projections through the API, and rebuild a new Google Sheet. This is the definitive disaster-recovery test.

## Stack-boundary tests

- stop Filament Manager and verify Moonraker continues updating Spoolman
- redeploy Spoolman and verify Filament Manager reconnects and reconciles
- verify neither service receives the other service's database credential
- remove and recreate `filament-services`, then verify recovery
- test independent image rollback for each stack
- verify Moonraker never depends on Swarm-internal DNS

## Authoritative implementation references

- Spoolman repository and supported databases: https://github.com/Donkie/Spoolman
- Spoolman installation and Docker port mapping: https://github.com/Donkie/Spoolman/wiki/Installation
- Spoolman configuration variables: https://github.com/Donkie/Spoolman/blob/master/.env.example
- Spoolman REST API: https://donkie.github.io/Spoolman/
- Moonraker Spoolman configuration: https://moonraker.readthedocs.io/en/stable/configuration/#spoolman
- Moonraker Spoolman integration API: https://moonraker.readthedocs.io/en/latest/external_api/integrations/#spoolman
- Fluidd Spoolman support: https://docs.fluidd.xyz/features/spoolman
- Google Sheets API: https://developers.google.com/workspace/sheets/api
- Docker Swarm stack deployment: https://docs.docker.com/engine/swarm/stack-deploy/
- PostgreSQL documentation: https://www.postgresql.org/docs/
