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
- `DELETE /spools/{id}`
- `POST /spools/{id}/measurements`
- `POST /spools/{id}/labels`
- `POST /spools/{id}/set-active`
- `POST /printer-context/active-spool/clear`

`POST /spools` accepts filament-only capacity and an optional full-spool gross reading; when tare is omitted, it infers tare as gross minus capacity and records the initial observation atomically. `PATCH /spools/{id}` accepts every setup field, explicit current-remaining correction, bounded free-text `location`, and `expected_version`. A changed current remaining amount appends an operator-correction usage event; supplying a location value or `null` establishes Filament Manager ownership. `DELETE /spools/{id}` deletes setup-only mistakes and their creation measurement, but archives any record with later measurement/use/print/calibration/NFC history. All paths queue supported Spoolman work atomically.

`POST /spools/{id}/set-active` is retained as the compatibility route for the Inventory **Load spool** action. It validates that the spool is available and projected and has a safe temperature from the newest non-archived exact profile or linked in-scope template, records an audited request, and queues `moonraker.spool_change.request`. It does not require publication, mutate canonical or Spoolman active state, or weaken the separate published-profile Cura print gate. The physical Klipper workflow performs state changes only at completed unload/load boundaries; periodic reconciliation observes the result.

Spool responses include a derived completed-print count. Every completed job counts once for each distinct spool appearing as the starting spool or in an M600 segment.

### Filament products and profiles

- `GET /filaments`
- `GET /filaments/{id}`
- `POST /filaments`
- `PATCH /filaments/{id}`
- `DELETE /filaments/{id}`
- `GET /filament-colors`
- `GET /profiles`
- `POST /profiles`
- `PUT /profiles/{id}/settings`
- `GET /profiles/{id}/exports/cura`
- `GET/POST /profiles/templates`
- `PUT /profiles/templates/{id}/settings`
- `PATCH /profiles/templates/{id}`

`POST /filaments` selects a current template snapshot and atomically creates the product plus its current inherited profile. `PATCH /filaments/{id}` corrects product setup and can relink a compatible current template while preserving sparse overrides. `DELETE /filaments/{id}` deletes only dependency-free setup mistakes and otherwise archives. Direct profile/template saves append hidden immutable snapshots, immediately become current, and queue projections. A template save also writes the next current profile snapshot for every linked filament while retaining each sparse explicit customization. Filament create/update resolves a shared case-insensitive solid palette, fixed Rainbow color, or one-to-three-sample product-specific multicolor palette. Only solid palette changes propagate to matching products. Color changes are rejected after retained spool use or print history. Configured-system seeding reports counts for printers, plates, and newly created recommended ASA templates.

### Build plates

- `GET /build-plates`
- `POST /build-plates/synchronize` (Administrator only; imports exact P-number A/B side meshes)
- `PATCH /build-plates/{id}`
- `GET /build-plates/{id}/image`
- `PUT /build-plates/{id}/image` (bounded image upload)
- `DELETE /build-plates/{id}/image`
- `POST /build-plates/{id}/surfaces` (Operator; creates the sole canonical Side B)
- `PATCH /build-plates/{id}/surfaces/{surface_id}`
- `POST /build-plates/{id}/select` (requires `surface_id`)
- `GET /build-plates/maintenance/status`
- `GET /build-plates/maintenance/events`
- `POST /build-plates/{id}/maintenance-events`
- `POST /build-plates/active/clear`

Maintenance events are append-only. Image uploads are decoded, dimension-bounded, metadata-stripped, normalized to WebP, and stored in PostgreSQL. Clearing the active plate first clears the loaded Moonraker mesh and then lets state reconciliation clear canonical context.

The Side B route derives `P<number>b` from the parent plate, rejects duplicates, and returns a mesh-unavailable side until Moonraker discovers that exact profile. Side responses include a derived completed-print count.

### Material profiles

- `GET /profiles/cura-settings/catalog`
- `POST /profiles`
- `PUT /profiles/{id}/settings`
- `GET /profiles/{id}/exports/cura`
- `POST /workstation-agents/{id}/cura-takeover`

The takeover request contains the complete reviewed source-ID set, explicit confirmation, and zero or more unique source-to-existing-template mappings. The server requires that content-hashed set to equal the latest reported source catalog, then validates active template scopes and single-use source/template constraints; directly applies mapped settings; cascades linked-profile inheritance; records mappings; enables management; and queues synchronization in one transaction. Unmapped sources create no canonical materials. Historical revision, publication, standalone Cura-import, template-rebase, and manual Cura-deployment routes remain hidden compatibility endpoints only.

### Calibration

- `POST /calibrations`
- `GET /calibrations/{id}`
- `POST /calibrations/{id}/steps/{step}/start`
- `POST /calibrations/{id}/steps/{step}/result`
- `GET /calibrations/{id}/suggestions`
- `POST /calibrations/{id}/apply-profile-settings`
- `POST /calibrations/{id}/apply-template-settings` (exact template-name confirmation)
- `DELETE /calibrations/{id}` (unapplied only)

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

### Account

- `GET /auth/users` (returns the one Administrator)
- `PATCH /auth/users/{id}` (edits the singleton username/display name)
- `POST /auth/change-password`

An empty database creates `admin` / `admin` and requires password replacement before other application routes are available. Existing single-account credentials survive upgrades. Identity or password changes revoke other sessions. Account creation, role, reset, and deactivation routes do not exist under the singleton contract.

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

### Physical nozzles

- `GET /nozzles`
- `POST /nozzles`
- `PATCH /nozzles/{id}`
- `POST /nozzles/{id}/install`
- `POST /nozzles/{id}/remove`
- `GET /nozzles/{id}/events`

Only one physical nozzle may be installed on a printer. `PATCH` may edit its unique code, including while installed, without rewriting lifecycle or print history. Responses derive completed-print and total-filament-use values from immutable print history; lifecycle events are append-only.

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
- `GET /diagnostics`
- `GET /diagnostics/log.txt`
- `GET /diagnostics/version`
- `GET /diagnostics/validation-runs`
- `POST /diagnostics/validation-runs` (Administrator only)
- `POST /diagnostics/projection-rebuild` (Administrator only)

Diagnostics responses contain only sanitized bounded checks, counts, timestamps, versions, and messages. The authenticated text route generates a non-cacheable attachment from that same sanitized overview and never includes URLs, SQL, tracebacks, credentials, or upstream response bodies. The version route compares the running version with the highest non-draft semantic release from the fixed public GitHub repository endpoint, includes testing prereleases, caches the result, and never returns the upstream body. Validation is read-only and persisted. Rebuild queues idempotent derived work and never performs a database restore.

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
