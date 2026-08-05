# 06 - Synchronization and Reconciliation Engine

## Principle

Synchronization is projection and reconciliation, not multi-master database replication. Filament Manager PostgreSQL is canonical; Spoolman and Google Sheets are external systems reached through supported interfaces.

The Spoolman stack is operationally independent. Filament Manager must tolerate its unavailability without corrupting canonical state, and Spoolman must continue serving Moonraker while Filament Manager is being redeployed.

## Transactional outbox

Every canonical mutation and its projection request commit in one PostgreSQL transaction. Workers claim jobs with `FOR UPDATE SKIP LOCKED`.

Suggested job types:

- `spoolman.vendor.upsert`
- `spoolman.filament.upsert`
- `spoolman.spool.upsert`
- `spoolman.spool.adjust_weight`
- `google.inventory.publish`
- `google.profile.publish`
- `google.plate.publish`
- `moonraker.active_spool.set`

## Connection model

Filament Manager uses the configurable Spoolman API URL. In production this normally resolves through the shared overlay network:

```text
http://spoolman_spoolman:8000
```

It must not use Spoolman's PostgreSQL connection string. The Spoolman database password is not mounted into the Filament Manager stack.

## Idempotency

Each external job contains:

- deterministic idempotency key
- canonical record version
- attempt counter
- next-attempt time
- last error class
- remote fingerprint
- completed timestamp

Out-of-order stale jobs complete without overwriting newer data.

## Spoolman inbound reconciliation

Moonraker updates Spoolman. Filament Manager listens by WebSocket where practical and periodically polls as a safety net.

For each spool:

1. Read the current Spoolman object through the API.
2. Compare it with the last acknowledged projection snapshot.
3. Create a canonical usage event for a valid printer-originated delta.
4. Update effective remaining mass.
5. Queue Google publication and any necessary Spoolman normalization.
6. Store a remote fingerprint and acknowledgment time.

## Measurement reconciliation

A manual or accepted scale measurement has higher physical confidence than expected mass.

```text
measured_net = gross_mass - tare_mass
variance = measured_net - expected_remaining_before_measurement
```

Store both the measurement and variance. Do not rewrite historical usage events.

## Double-counting prevention

Do not independently apply both continuous scale loss and Moonraker consumption over the same interval. Initially, scale data is a periodic physical correction while Moonraker remains the consumption source.

## Conflict classes

- canonical metadata newer than Spoolman: project canonical metadata
- Spoolman usage newer than acknowledgment: import usage delta
- manual measurement newer than usage estimate: accept measurement and record variance
- unknown Spoolman edit: flag for review before overwriting identity-sensitive fields
- Google human edit: warn and overwrite or pause publication according to policy

## Failure isolation tests

Required tests include:

- Filament Manager stack stopped while Moonraker records usage in Spoolman
- Spoolman stack stopped while Filament Manager queues projection jobs
- Spoolman upgrade with pending usage reconciliation
- central PostgreSQL available to one database but the other role is revoked or misconfigured
- shared overlay network removed and recreated

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
