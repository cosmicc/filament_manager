# 06 - Synchronization and Reconciliation Engine

## Principle

Synchronization is projection and reconciliation, not multi-master database replication. Filament Manager PostgreSQL is canonical; Spoolman and Google Sheets are external systems reached through supported interfaces.

The Spoolman service is operationally distinct. Filament Manager must tolerate its unavailability without corrupting canonical state, and an unchanged Spoolman service must continue serving Moonraker while the Filament Manager services are updated.

## Transactional outbox

Every canonical mutation and its projection request commit in one PostgreSQL transaction. Workers claim jobs with `FOR UPDATE SKIP LOCKED`. Multiple configured dispatchers claim one job at a time, and a bounded lock timeout allows a replacement worker to reclaim work abandoned by a terminated process. Per-object PostgreSQL advisory locks prevent concurrent retries or convergence from creating duplicate remote objects.

Suggested job types:

- `spoolman.vendor.upsert`
- `spoolman.filament.upsert`
- `spoolman.spool.upsert`
- `spoolman.spool.adjust_weight`
- `google.inventory.publish`
- `google.profile.publish`
- `google.plate.publish`
- `moonraker.spool_change.request`
- `moonraker.state.reconcile`
- `moonraker.printer_info.reconcile`

## Connection model

Filament Manager uses the configurable Spoolman API URL. In production this normally resolves through the shared overlay network:

```text
http://spoolman:8000
```

The optional separate-stack deployment uses `http://spoolman_spoolman:8000`. Filament Manager must not use Spoolman's PostgreSQL connection string. The Spoolman database password is not mounted into the Filament Manager services.

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

Moonraker updates Spoolman. Filament Manager performs a complete API-only safety sweep every minute by default. Canonical mutations also enqueue immediate projection jobs, so the sweep is recovery and drift repair rather than the normal delivery delay.

For each spool:

1. Provision and validate managed custom fields, then read every paginated Spoolman object through the API.
2. Compare it with the last acknowledged projection snapshot.
3. Create a canonical usage event for a valid printer-originated delta.
4. Update effective remaining mass.
5. Queue Google publication and any necessary Spoolman normalization.
6. Store a remote fingerprint and acknowledgment time.
7. Converge every canonical vendor, filament, and spool after importing usage, omitting remaining weight from metadata-only updates.

## Moonraker inbound reconciliation

The worker reads Moonraker's supported active Spoolman ID, persisted Filament Manager physical-spool macro state, and exact P-number bed-mesh state every 15 seconds by default. After one-time initialization, the macro's last completed physical boundary wins over a conflicting direct active-ID edit. A valid non-null direct selection made in `idle`, `load_select`, or `manual_select` is first delivered as a guarded Fluidd target; Moonraker/Spoolman is then restored to the physical ID before canonical active-spool alignment. Direct clears, invalid selections, and drift during other phases are repaired without target capture. The worker also publishes the bounded current product-material GUID, eligible spool ID, label, and profile-temperature catalog used by print and manual-load prompts. A separate 5-minute job reads only the approved sanitized printer-information fields. Each state surface may make safe partial progress when another endpoint is unavailable, then the outbox job retries the failed portion.

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

- Filament Manager services stopped while Moonraker records usage in Spoolman
- Spoolman service stopped while Filament Manager queues projection jobs
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
