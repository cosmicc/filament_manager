# 03 - Canonical Data Model

## Modeling principles

- UUID technical keys and human business IDs that become immutable when retained history begins.
- Numeric types for mass, dimensions, density, flow, and money.
- Immutable event tables for measurements, usage, and calibration results.
- Versioned material templates, sparse product overrides, and immutable resolved profile snapshots.
- Explicit projection state for Spoolman and Google.
- Soft archive rather than destructive delete for referenced records.

## Core entities

### vendor

Manufacturer identity and aliases.

### filament_product

A purchasable material definition: material, filler, finish, color, product/grade/hardness, diameter, tolerance, density, nominal weight, and vendor.

### filament_color

A remembered case-insensitive solid color name and display sample. The first spelling is retained for display. Changing a solid palette updates every matching product mirror so current and future filaments with names such as `Red` remain visually consistent. Rainbow is a color with one fixed spectrum. Multicolor products own one, two, or three samples directly so unrelated multicolor products never share a palette. A product color cannot change after retained spool use or print history exists.

### spool

A physical spool with `spool_code`, purchased net filament weight, tare mass, optional purchase cost/currency, current expected remaining mass, status, bounded free-text location, internal location-ownership state, Spoolman ID, and label data. Cost per gram is derived with exact decimal arithmetic as purchase cost divided by purchased net filament weight. The code and linked filament may be corrected only while the record has no retained measurement/use/print/calibration/NFC history, then become immutable. Existing rows with no canonical location may adopt one remote location; a local edit or clear makes the canonical value authoritative.

### spool_measurement

Immutable gross-weight observation:

- source: manual, scale, import, correction
- gross mass
- tare used
- calculated net mass
- accepted/rejected state
- device and sequence when applicable
- confidence and uncertainty
- operator and notes

### spool_usage_event

Consumption or adjustment event with source, printer, print job, mass delta, event time, and idempotency key.

### printer

Printer identity, server-only Moonraker endpoint, installed physical-nozzle reference, manufacturer/model, extruder type, kinematics, build volume, sanitized host/version information, active plate, notes, and integration state. Documented Moonraker/Klipper fields may refresh discovered values while user-maintained hardware descriptions remain manual.

### nozzle and nozzle_lifecycle_event

A physical nozzle belongs permanently to one printer and has an editable human code that is case-insensitively unique within that printer, diameter, construction material, manufacturer/product, optional purchase and installation metadata, lifecycle status, notes, and optimistic version. Code edits do not rewrite append-only lifecycle or print attribution. A printer has at most one installed nozzle, and a nozzle cannot be installed on a printer other than its owner. Append-only lifecycle events retain installation and removal boundaries. Completed-print count and total filament use derive from immutable print history captured while the nozzle was installed.

### build_plate

Physical plate record. Business IDs are exact uppercase `P<number>` values; `P1` through `P5` are the initial seeds. Fields include display name, description, manufacturer/product, shape/dimensions, magnetic/flexible properties, preferred materials, temperature limit, physical condition/status, last clean, notes, and bounded sanitized WebP picture bytes/media/checksum/version stored in PostgreSQL.

### build_plate_surface

One printable side of a physical plate. Side A uses the physical plate code (`P4`); Side B uses a lowercase `b` suffix (`P4b`). Fields include surface material, smooth/textured finish, same-named Klipper mesh, mesh availability/check time, last mesh calibration, and notes. The sole Side B may be created manually but starts unavailable. Missing Moonraker meshes do not delete the physical plate, side, or metadata.

### build_plate_maintenance_event

Append-only cleaning or side-specific mesh-calibration evidence. Plate-level day and print-count thresholds calculate reminder state without rewriting the event history.

### material_profile

Immutable internal settings snapshots scoped to:

- filament product
- printer
- nozzle diameter
- optional layer-height range

Every current snapshot directly references the current `material_template_revision`, stores only semantically different permitted `setting_overrides`, and caches the complete resolved values in the typed columns plus `cura_extensions`. Typed values include separate regular and initial-layer build-plate temperatures. The resolved snapshot inherits template-owned print-speed, smooth-time, and acceleration values and may reference a preferred plate side. Every cooling control, pressure advance, and ironing flow/speed/line-spacing value may enter product overrides; Cura quality profiles own ironing enablement. Direct saves append the next current immutable snapshot and queue projections without an operator-facing draft or publication state.

### material_template and material_template_revision

The template is a mutable identity for one material type and one exact printer-owned physical nozzle; its printer and cached diameter must match that nozzle. Its canonical Cura identity is `Template <material type>` under the `Template` brand. Only one active template exists per normalized material family and physical nozzle. Revisions are hidden complete immutable settings snapshots and exclusively own print-speed settings, smooth time, and the approved print/feature/support/travel acceleration values. Creating a filament product links its first current profile to the template's current snapshot, records only permitted product-specific differences such as density, cooling, pressure advance, and ironing, and computes the resolved snapshot. A direct template save immediately creates the next current snapshot for every linked profile while preserving its permitted explicit override keys.

### cura_takeover_mapping

Immutable provenance for one Administrator-confirmed workstation source-to-existing-template choice. Unique agent/source and agent/template constraints prevent ambiguous reuse. It records the sanitized source type/name and the exact applied template snapshot; unmapped sources have no canonical material record.

### cura_managed_edit_receipt

Idempotently records one content checksum reported for a known managed Cura GUID and the current template/profile snapshot it created. Unknown GUIDs and new Cura materials never create canonical records.

### cura_recovery_snapshot

Immutable, sanitized operational Cura configuration captured only while Cura is closed. It is scoped to one workstation agent, discovered installation identity, and exact Cura version. The payload is checksummed and bounded and contains complete non-sensitive allowlisted printer/extruder/definition-change documents—including opaque start/end G-code and printer options—plus user definitions and variants, quality/profile state, setting visibility, safe preferences, and semantic plugin names/versions. It never stores workstation paths, account sessions, credentials, network endpoints, or plugin executable files. Retention keeps the fifteen newest distinct automatic snapshots for each workstation installation and Cura version; named points do not consume that quota and remain until explicit deletion. A reset or large deletion is recorded as blocked state without replacing the last known-good snapshot.

### cura_recovery_restore

One confirmed Administrator recovery request copied from an immutable snapshot. The snapshot may originate from any paired workstation, but the request is leased only to the selected target agent and an installation reporting the exact matching Cura version. It retains a bounded success/failure result and never exposes the stored file payload to the browser. The target workstation creates its own rollback backup before applying the restore.

### calibration_session

Tracks a wizard run for one filament, printer, nozzle, and optional plate. Contains ordered step records and final profile version.

### calibration_step

One of temperature, flow, pressure advance, retraction, dimensional size/hole compensation, overhang, or ironing. Dimensional results retain X/Y/Z, hole, shaft, and wall design/measured values. Material outputs include Cura expansion, flow, and shrinkage; printer-geometry correction percentages remain non-applying review evidence. Each step stores test parameters, raw measurements, calculated/selected result, status, and notes.

### print_job, print_material_segment, and print_assessment

`print_job` merges supported Moonraker live/history records and retains one immutable start-state snapshot: printer, physical nozzle, physical spool, product, exact material-profile revision, plate side, sliced metadata, actual usage, complete streamed-file hash, and bounded inspection evidence. Records imported without reconstructable state remain explicitly unresolved. `print_material_segment` records the ordered spool intervals created by M600 transitions and their usage. When a completed, failed, or cancelled job reaches a terminal state, each exact spool receives one idempotent actual-use event aggregated from its segments; a lower Spoolman-imported boundary wins to prevent double subtraction, and unavailable actual use has no predicted fallback. `print_assessment` appends quality revisions and never overwrites an earlier score. Completed statistics count the captured nozzle and side once and each distinct start/segment spool once per completed job.

### diagnostic_run and worker_heartbeat

`diagnostic_run` persists one bounded sanitized recovery-validation result without mutating canonical business records. `worker_heartbeat` records current worker liveness and a safe state summary. Projection rebuilds are represented by ordinary idempotent outbox jobs.

### application_setting

Versioned Administrator policy, including the G-code inspection mode. Inspection defaults to `warn`; `block` pauses print release when exact profile state, inspection, or supported comparisons cannot be verified.

### notification and user_notification_state

Persistent, deduplicated operational conditions plus per-account read timestamps. When a resolved condition recurs, all read state is cleared so the notification is visible again.

### nfc_tag

Maps a tag UID to one spool. UID is unique but not secret. Store tag technology, first seen, last seen, and status.

### device

Registered scale or NFC adapter with credential hash, type, location, firmware, status, and last-seen time.

### projection_state

Tracks remote object IDs, fingerprints, last successful publication, error, and retry state for Spoolman and Google.

### outbox_job

Durable external work item created in the same transaction as the canonical change. Its aggregate version is a 64-bit integer so both canonical record versions and microsecond manual system-job identities fit exactly. It retains the exact newest failure time and sanitized error class/message. Superseded rows remain historical, while only pending, running, retrying, or current dead work counts as actionable queue debt.

### audit_event

Append-only record of actor, source, action, object, before/after JSON, correlation ID, and timestamp.

## Important relationships

```text
vendor 1---n filament_product 1---n spool
filament_product 1---n material_profile
printer 1---n material_profile
printer 1---n calibration_session
printer 1---n print_job 1---n print_material_segment
print_job 1---n print_assessment
build_plate 1---n calibration_session
build_plate 1---n build_plate_maintenance_event
spool 1---n spool_measurement
spool 1---n spool_usage_event
spool 1---n nfc_tag
user n---n notification (through user_notification_state)
```

## Weight state

Store:

- `remaining_mass_expected_g`
- `remaining_mass_measured_g`
- `remaining_mass_effective_g`
- `last_measurement_at`
- `last_usage_event_at`
- `weight_confidence`

Effective mass normally uses the latest accepted measurement adjusted by subsequent usage events. It must be clamped to the physically valid interval unless an administrator records an override.

## Profile settings

Stable typed fields:

- build volume temperature (canonical chamber temperature)
- extruder temperature
- bed temperature
- flow percentage
- default and advanced print speeds
- retraction distance and speed
- cooling enabled, minimum, maximum
- support overhang angle
- maximum branch angle
- pressure advance
- filament density
- preferred build-plate side
- optional ironing fields

Store only approved less-common Cura Material Settings keys in `cura_extensions JSONB` with a schema version. Unknown settings and machine-level keys are rejected.

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
