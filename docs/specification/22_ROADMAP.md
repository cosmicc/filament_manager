# 22 - Roadmap

## Phase 0 - Infrastructure preparation

- central PostgreSQL databases and roles
- `pg_hba.conf` restrictions
- combined-stack `filament-services` overlay
- distinct Spoolman service
- persistent Spoolman data volume
- stable LAN DNS name for Moonraker

## Phase 1 - Canonical foundation

- Filament Manager schema, migrations, audit, outbox
- users, printers, spools, profiles, build plates, measurements
- Filament Manager web and worker services

## Phase 2 - Workbook import and manual workflow

- dry-run import
- validation and duplicate report
- labels and QR lookup
- manual gross-weight entry

## Phase 3 - Spoolman and printer integration

- API projection and custom fields
- WebSocket/poll reconciliation
- Moonraker active-spool tracking
- failure-isolation test while Filament Manager is stopped
- independent Spoolman upgrade procedure

## Phase 4 - Read-only Google publication

- protected tabs
- deterministic rebuild
- unexpected-edit detection

## Phase 5 - Profiles, plates, and wizard

- Cura export
- P1-P5 initial physical build plates, `P<number>`/`P<number>b` side discovery, and one-to-one side-to-mesh mappings
- calibration workflow

## Phase 6 - Scale and NFC

- adapter registration
- scale telemetry and stable measurements
- NFC identity mapping
- automatic active-spool association

## Later enhancements

- multiple printers sharing the standalone Spoolman service
- dryer-slot and storage-location modeling
- notification policies
- richer profile export targets
- calibrated spool tare library by vendor/product
- high-availability review for the shared endpoint after usage justifies it

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
