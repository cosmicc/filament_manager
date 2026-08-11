# 24 - Implementation Checklist

## Infrastructure

- [ ] central PostgreSQL reachable from approved Swarm nodes
- [ ] `filament_manager` database and `filament_manager_user`
- [ ] `spoolman` database and `spoolman_user`
- [ ] no cross-database grants
- [ ] SCRAM and `pg_hba.conf` restrictions
- [ ] combined-stack `filament-services` overlay network
- [ ] durable Spoolman and Filament Manager volumes with valid multi-node placement or shared storage
- [ ] stable LAN DNS name for Spoolman

## Spoolman service

- [ ] tested image tag pinned
- [ ] database password supplied only through the scoped Spoolman environment
- [ ] PostgreSQL connection verified
- [ ] container port 8000 published as 7912
- [ ] health check passes
- [ ] one replica and stop-first update policy
- [ ] CORS origin is exact and not wildcard
- [ ] Moonraker and Fluidd verified
- [ ] stop-first upgrade and rollback tested

## Filament Manager services

- [ ] root combined stack file validated
- [ ] no mounted application Docker config; deployer-specific settings are environment variables
- [ ] canonical database URL assembled from protected stack variables
- [ ] joins the combined `filament-services` overlay
- [ ] Spoolman base URL configurable
- [ ] no Spoolman database credential passed to Filament Manager
- [ ] one Moonraker printer name, URL, nozzle diameter, and optional credential validated
- [ ] health/readiness/metrics endpoints
- [ ] migration locking
- [ ] service restart tested without corrupting Spoolman state

## Canonical data and import

- [ ] all workbook columns mapped
- [ ] dry-run import report
- [ ] duplicate and validation checks
- [ ] audit log
- [ ] immutable measurements and corrections

## Synchronization

- [ ] outbox tables and workers
- [ ] API-only Spoolman projection
- [ ] unknown `extra` fields preserved
- [ ] inbound usage reconciliation
- [ ] restart and backlog recovery
- [ ] stack/network outage tests

## Google publication

- [ ] native Sheet created
- [ ] protected application-managed ranges
- [ ] deterministic full rebuild
- [ ] unexpected-edit policy
- [ ] publication lag monitoring

## Profiles and plates

- [ ] all requested Cura fields typed
- [ ] versioned extension settings
- [ ] Cura export template
- [ ] P1-P5 seeded
- [ ] mesh mapping tested
- [ ] preferred plate warnings

## Calibration wizard

- [ ] temperature
- [ ] flow
- [ ] pressure advance
- [ ] retraction
- [ ] overhang
- [ ] optional ironing
- [ ] repeat/invalidation behavior
- [ ] final profile publication

## Manual operations and future hardware

- [ ] QR/label generation
- [ ] manual gross-weight form
- [ ] variance confirmation
- [ ] measurement history
- [ ] device table and credentials
- [ ] scale event schema
- [ ] NFC event schema
- [ ] replay protection
- [ ] adapter simulator
