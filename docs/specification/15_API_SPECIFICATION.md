# 15 - Application API Specification

## Conventions

- base path `/api/v1`
- JSON request/response
- UUID resource IDs plus human codes
- UTC ISO-8601 timestamps
- `ETag` or record-version preconditions on updates
- idempotency key on measurement and device-event creation
- authenticated administrative writes

## Core resources

### Inventory

- `GET /spools`
- `POST /spools`
- `GET /spools/{id}`
- `PATCH /spools/{id}`
- `POST /spools/{id}/measurements`
- `POST /spools/{id}/labels`
- `POST /spools/{id}/set-active`
- `POST /printer-context/active-spool/clear`

`PATCH /spools/{id}` accepts a bounded free-text `location` plus `expected_version`. Supplying a value or `null` establishes Filament Manager ownership and queues the Spoolman projection atomically.

`POST /spools/{id}/set-active` is retained as the compatibility route for the Inventory **Load spool** action. It validates that the spool is available, projected, and has a current published profile for the configured printer/nozzle, records an audited request, and queues `moonraker.spool_change.request`. It does not mutate canonical or Spoolman active state. The physical Klipper workflow performs those changes only at completed unload/load boundaries; periodic reconciliation observes the result.

### Filament products and profiles

- `GET /filaments`
- `GET /filaments/{id}`
- `POST /filaments`
- `PATCH /filaments/{id}`
- `GET /filament-colors`
- `GET /profiles`
- `POST /profiles`
- `POST /profiles/{id}/publish`
- `POST /profiles/{id}/revisions`
- `GET /profiles/{id}/exports/cura`
- `GET/POST /profiles/templates`
- `PATCH /profiles/templates/{id}`
- `POST /profiles/templates/{id}/revisions`
- `POST /profiles/templates/{id}/revisions/{revision_id}/publish`

`POST /filaments` may select a published template revision and atomically creates the product plus its copied draft profile. Filament create/update resolves the case-insensitive remembered color sample and propagates a changed sample to matching products with their projection jobs in the same transaction.

### Build plates

- `GET /build-plates`
- `POST /build-plates/synchronize` (Administrator only; imports exact P-number A/B side meshes)
- `PATCH /build-plates/{id}`
- `PATCH /build-plates/{id}/surfaces/{surface_id}`
- `POST /build-plates/{id}/select` (requires `surface_id`)
- `GET /build-plates/maintenance/status`
- `GET /build-plates/maintenance/events`
- `POST /build-plates/{id}/maintenance-events`
- `POST /build-plates/active/clear`

Maintenance events are append-only. Clearing the active plate first clears the loaded Moonraker mesh and then lets state reconciliation clear canonical context.

### Material profiles

- `GET /profiles/cura-settings/catalog`
- `POST /profiles/import-cura-material`
- `POST /profiles`
- `POST /profiles/{id}/publish`
- `GET /profiles/{id}/exports/cura`

### Calibration

- `POST /calibrations`
- `GET /calibrations/{id}`
- `POST /calibrations/{id}/steps/{step}/start`
- `POST /calibrations/{id}/steps/{step}/result`
- `POST /calibrations/{id}/publish-profile`

### Print history and inspection

- `GET /prints`
- `GET /prints/{id}`
- `GET /prints/profile-statistics`
- `POST /prints/{id}/assessments`

Print responses preserve exact start-state snapshots, bounded G-code inspection evidence, material-change segments, actual usage, explicit unresolved legacy state, and append-only quality revisions. Profile statistics use the latest assessment for each print.

### Notifications and operational policy

- `GET /notifications`
- `POST /notifications/{id}/read`
- `POST /notifications/actions/read-all`
- `GET /settings/operational`
- `PATCH /settings/operational` (Administrator only)

The settings update requires optimistic concurrency and supports `warn` or `block` G-code inspection policy. Notifications are persistent conditions with per-user read state.

### Accounts

- `GET /auth/users` (Administrator only)
- `POST /auth/users` (Administrator only)
- `PATCH /auth/users/{id}` (Administrator only)
- `POST /auth/users/{id}/reset-password` (Administrator only)
- `POST /auth/change-password`

New and reset accounts must replace their temporary password before using other application routes. Deactivation and reset revoke prior sessions; last-Administrator and self-deactivation safeguards apply.

### Integrations

- `GET /integrations/status`
- `POST /integrations/spoolman/reconcile`
- `POST /integrations/google/publish`
- `POST /integrations/google/rebuild`

### Printers

- `GET /printers`
- `PATCH /printers/{id}` (Administrator only)
- `POST /printers/{id}/synchronize-info` (Administrator only)

Printer responses omit Moonraker addresses and credentials. Synchronization returns only bounded documented metadata persisted to the canonical printer record.

### Devices

- `POST /device-events/scale`
- `POST /device-events/nfc`
- `GET /devices`

### Operations

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`
- `GET /imports/workbook`
- `POST /imports/workbook/dry-run`
- `POST /imports/workbook/{run_id}/commit`
- `GET /jobs`
- `POST /jobs/{id}/retry`
- `GET /audit-events`

## WebSocket/SSE events

- spool updated
- measurement accepted/rejected
- active spool changed
- active plate changed
- calibration step changed
- projection job failed/recovered
- device online/offline

## Error model

Return stable machine codes such as:

- `record_version_conflict`
- `invalid_weight`
- `unknown_spool`
- `profile_incomplete`
- `spool_change_not_ready`
- `gcode_inspection_blocked`
- `password_change_required`
- `plate_mesh_unavailable`
- `spoolman_unavailable`
- `google_publish_failed`

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
