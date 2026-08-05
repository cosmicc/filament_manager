# 21 - UI and UX Specification

## Navigation

- Dashboard
- Spools
- Filaments
- Profiles
- Calibration Wizard
- Build Plates
- Printers
- Labels
- Integrations
- Activity/Audit
- Settings

## Dashboard

Show:

- active spool and remaining mass
- active build plate and mesh
- current print and usage status
- low/empty inventory
- calibration tasks
- Spoolman/Moonraker/Google health
- last accepted measurement

## Spool detail

- label/QR
- current effective, measured, and expected mass
- tare and measurement history
- usage history
- product/profile
- active printer/dryer location
- Spoolman projection status
- manual weigh action
- NFC association later

## Calibration wizard UX

Use a persistent stepper with the exact six steps. Each step has instructions, test settings, file/job link, result fields, notes, and “repeat” action. Show downstream invalidation before allowing an earlier result to change.

## Build plate UX

Cards for P1-P5 with surface, condition, mesh, last clean, last calibration, and material preferences. The active plate is visually explicit.

## Google status

Display publication time, rows updated, drift warnings, and rebuild action. Never suggest editing the Sheet as a normal workflow.

## Manual weight UX

Large numeric input, selected spool identity, tare, computed remaining mass, variance, and confirmation for suspicious values. Optimize for mobile use near the printer.

## Accessibility

Keyboard navigation, semantic labels, adequate contrast, non-color status indicators, and clear error recovery.

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
