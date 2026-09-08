# 05 - Read-Only Google Sheet Publication

## Implemented contract (0.7.9)

Settings now provides Google OAuth connection, disconnect and Sync now. The worker creates a native Filament Manager workbook with 24 linked/filterable tabs, including archived business records and immutable print/profile/template settings. See [Google setup and workbook behavior](../GOOGLE_SHEETS.md) and [agent workflow](../../skills/google-publication.md) for the authoritative current contract.

Publishing uses explicit business-column allowlists, encrypted offline access, complete periodic content comparison, print deferral, shared retries and staged atomic replacement into stable tab IDs. It does not export credentials or binaries. Owner edits are warned and overwritten on changed or forced publication; continuous human-edit detection and the older configurable pause policy below remain design proposals, not implemented capabilities. The original Inventory tab is retained but superseded by Spools. The remainder of this document records the original design proposal where it differs from the current contract.

## Purpose

Provide a convenient Google Drive view of current filament, profile, plate, and calibration information without making the Sheet authoritative.

## Direction

```text
PostgreSQL -> Filament Manager publisher -> Google Sheet
```

No automatic Google-to-database synchronization occurs after the initial workbook import.

## Access model

- Service account: editor of the publication spreadsheet.
- Human users: viewer or commenter where possible.
- Application-managed ranges: protected.
- If the owner retains edit capability, Filament Manager still treats the workbook as read-only and overwrites unsupported edits during full publication.

## Proposed tabs

### Dashboard

Counts, remaining inventory, low/empty spools, estimated inventory value, calibrations pending, projection health, and last publication time.

### Inventory

One row per physical spool with the current canonical values and original workbook-compatible columns.

### Filament Profiles

One row per current material profile, including printer, nozzle, settings, and preferred plate. Hidden immutable snapshot IDs may be retained for traceability without presenting a revision workflow.

### Build Plates

All canonical physical P-number plates, including initial P1-P5 and later Moonraker-discovered records, plus nested A/B side code, surface material, finish, mesh profile/availability/check/calibration state, physical status/maintenance, and notes.

### Calibration Status

Current sessions, completed steps, selected results, and whether results have been applied to the current profile.

### Lists

Controlled vocabulary used by the app and displayed for reference.

### Activity Summary

Recent measurements, print usage, corrections, and publication events without sensitive security data.

## Publication metadata

Every row includes:

- internal record UUID
- human code
- record version
- updated timestamp
- published timestamp

## Update strategy

- Queue a targeted row update after canonical transactions.
- Coalesce rapid updates.
- Run periodic full comparison.
- Support complete rebuild into a temporary tab set and atomic rename/swap where practical.
- Rate-limit and batch writes.
- Preserve formatting and protected ranges through template-aware publishing.

## Human-edit detection

Store a hash of the last published managed range. If a managed cell changed unexpectedly:

1. record a warning;
2. optionally copy the human value into an audit note;
3. publish the canonical value again;
4. never import it automatically.

## Workbook migration

The existing `.xlsx` is imported once. The application creates a new native Google Sheet publication or converts a copy, then protects it. The original workbook remains a reference/backup artifact.

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
