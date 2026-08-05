# 14 - Future NFC and Spool Identification

## Goal

Detect which spool is placed in the dryer connected to the printer and set the operational active spool with minimal manual work.

## Tag model

- one active NFC tag may identify one spool
- tag UID is unique
- tags can be replaced, disabled, or reassigned with audit history
- UID is an identifier, not proof of authorization

## Event flow

```text
NFC reader -> authenticated adapter event -> Filament Manager lookup
           -> operator policy check -> Moonraker set active spool
           -> record dryer/printer location and event
```

## Policies

- `detect_only`: display the detected spool
- `prompt`: ask for confirmation before activation
- `auto_when_idle`: set active only while printer is idle
- `strict`: reject unknown tags and warn

Default should be `prompt` until hardware reliability is established.

## Reader event

Include device ID, UID, time, present/removed state, sequence, and optional signal quality. Debounce repeated reads.

## Manual fallback

QR/label selection remains available at all times. A failed NFC reader must not block printing.

## Security

Use a per-device credential, replay protection, rate limiting, and network segmentation. Do not expose the reader directly to Moonraker or PostgreSQL.

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
