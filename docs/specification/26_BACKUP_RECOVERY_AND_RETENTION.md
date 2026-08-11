# 26 - Backup, Recovery, and Data Retention

## Backup set

- canonical `filament_manager` PostgreSQL database
- distinct Spoolman `spoolman` PostgreSQL database
- both production stack files
- encrypted stack-variable backup according to operations policy
- Spoolman local data directory where operationally required
- Google Sheet ID and template metadata
- label and Cura export templates

## Independent restore objectives

The stack boundary requires two restoration paths:

### Filament Manager restore

Restore the canonical database, migrations, stack, and protected variable inventory. Spoolman may remain online while this occurs. After recovery, reconcile usage accumulated during the outage.

### Spoolman restore

Restore the Spoolman database and stack independently. If the database cannot be restored, initialize a blank database, reproject canonical records through the API, and reconcile printer-originated state.

## Retention

- audit and measurement history: retain indefinitely unless policy changes
- device raw telemetry: short configurable retention, summarized afterward
- completed outbox jobs: retain for troubleshooting, then archive
- calibration artifacts: retain with profile versions
- Spoolman logs: retain according to centralized logging policy

## Quarterly recovery test

1. restore `filament_manager` to an isolated environment;
2. restore or initialize `spoolman` separately;
3. deploy both services on an isolated combined-stack overlay;
4. rebuild Spoolman projections through the API;
5. create a new Google publication workbook;
6. compare counts, weights, profile versions, plates, and calibration status;
7. simulate a Filament Manager outage while usage continues in Spoolman;
8. document recovery time and discrepancies.

## RPO and RTO

Set explicit targets based on the central PostgreSQL backup platform. Both databases should receive WAL-aware protection where available, but their restore priorities may differ: printer usage continuity favors Spoolman availability, while full business-state integrity depends on Filament Manager.

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
