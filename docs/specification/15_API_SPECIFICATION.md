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

`PATCH /spools/{id}` accepts a bounded free-text `location` plus `expected_version`. Supplying a value or `null` establishes Filament Manager ownership and queues the Spoolman projection atomically.

### Filament products and profiles

- `GET /filaments`
- `POST /filaments`
- `GET /profiles`
- `POST /profiles`
- `POST /profiles/{id}/publish`
- `GET /profiles/{id}/exports/cura`
- `GET/POST /profiles/templates`
- `PATCH /profiles/templates/{id}`
- `POST /profiles/templates/{id}/revisions`
- `POST /profiles/templates/{id}/revisions/{revision_id}/publish`

`POST /filaments` may select a published template revision and atomically creates the product plus its copied draft profile.

### Build plates

- `GET /build-plates`
- `POST /build-plates/synchronize` (Administrator only; imports exact P-number A/B side meshes)
- `PATCH /build-plates/{id}`
- `PATCH /build-plates/{id}/surfaces/{surface_id}`
- `POST /build-plates/{id}/select` (requires `surface_id`)
- `POST /build-plates/{id}/maintenance`

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

### Integrations

- `GET /integrations/status`
- `POST /integrations/spoolman/reconcile`
- `POST /integrations/google/publish`
- `POST /integrations/google/rebuild`

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
