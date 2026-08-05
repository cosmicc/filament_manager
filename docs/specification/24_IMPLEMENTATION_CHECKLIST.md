# 24 - Implementation Checklist

## Infrastructure

- [ ] central PostgreSQL reachable from approved Swarm nodes
- [ ] `filament_manager` database and `filament_manager_user`
- [ ] `spoolman` database and `spoolman_user`
- [ ] no cross-database grants
- [ ] SCRAM and `pg_hba.conf` restrictions
- [ ] external `filament-services` overlay network
- [ ] external Spoolman data volume
- [ ] stable LAN DNS name for Spoolman

## Standalone Spoolman stack

- [ ] tested image tag pinned
- [ ] database password stored as Docker secret
- [ ] PostgreSQL connection verified
- [ ] container port 8000 published as 7912
- [ ] health check passes
- [ ] one replica and stop-first update policy
- [ ] CORS origin is exact and not wildcard
- [ ] allowed hosts configured for reverse proxy
- [ ] Moonraker and Fluidd verified
- [ ] independent upgrade and rollback tested

## Filament Manager stack

- [ ] separate stack file
- [ ] canonical database URL secret
- [ ] joins `filament-services`
- [ ] Spoolman base URL configurable
- [ ] no Spoolman DB secret mounted
- [ ] health/readiness/metrics endpoints
- [ ] migration locking
- [ ] independent restart tested without Spoolman interruption

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
