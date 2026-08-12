# 03 - Canonical Data Model

## Modeling principles

- UUID technical keys, immutable human business IDs.
- Numeric types for mass, dimensions, density, flow, and money.
- Immutable event tables for measurements, usage, and calibration results.
- Versioned generic material templates and product-owned material profiles.
- Explicit projection state for Spoolman and Google.
- Soft archive rather than destructive delete for referenced records.

## Core entities

### vendor

Manufacturer identity and aliases.

### filament_product

A purchasable material definition: material, filler, finish, color, product/grade/hardness, diameter, tolerance, density, nominal weight, and vendor.

### filament_color

A remembered case-insensitive color name and six-digit screen sample. The first spelling is retained for display. Changing the sample updates every matching product mirror so current and future filaments with names such as `Red` or `Temp Sensitive` remain visually consistent.

### spool

A physical spool with immutable `spool_code`, tare mass, purchase details, current expected remaining mass, status, bounded free-text location, internal location-ownership state, Spoolman ID, and label data. Existing rows with no canonical location may adopt one remote location; a local edit or clear makes the canonical value authoritative.

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

Printer identity, server-only Moonraker endpoint, nozzle diameter/material, manufacturer/model, extruder type, kinematics, build volume, sanitized host/version information, active plate, notes, and integration state. Documented Moonraker/Klipper fields may refresh discovered values while user-maintained hardware descriptions remain manual.

### build_plate

Physical plate record. Business IDs are exact uppercase `P<number>` values; `P1` through `P5` are the initial seeds. Fields include display name, description, manufacturer/product, shape/dimensions, magnetic/flexible properties, preferred materials, temperature limit, physical condition/status, last clean, and notes.

### build_plate_surface

One printable side of a physical plate. Side A uses the physical plate code (`P4`); Side B uses a lowercase `b` suffix (`P4b`). Fields include surface material, smooth/textured finish, same-named Klipper mesh, mesh availability/check time, last mesh calibration, and notes. Missing Moonraker meshes do not delete the physical plate, side, or metadata.

### material_profile

Versioned settings scoped to:

- filament product
- printer
- nozzle diameter
- optional layer-height range

Contains the approved Cura Material Settings values, including Cura Klipper Settings pressure advance and smooth time. Profiles are scoped to a filament product, printer, and nozzle and may reference a preferred plate side. Publishing creates a new immutable version rather than editing historical versions in place.

### material_template and material_template_revision

The template is a mutable identity for one generic material type, printer, nozzle, and filament diameter. Revisions store complete validated settings snapshots and become immutable when published. Creating a filament product from a published revision copies those settings into Material Profile version 1 in draft state, overrides generic density with the product's canonical density, and records revision provenance on both rows.

### calibration_session

Tracks a wizard run for one filament, printer, nozzle, and optional plate. Contains ordered step records and final profile version.

### calibration_step

One of temperature, flow, pressure advance, retraction, dimensional size/hole compensation, overhang, or ironing. Stores test parameters, raw measurements, calculated/selected result, status, and notes.

### nfc_tag

Maps a tag UID to one spool. UID is unique but not secret. Store tag technology, first seen, last seen, and status.

### device

Registered scale or NFC adapter with credential hash, type, location, firmware, status, and last-seen time.

### projection_state

Tracks remote object IDs, fingerprints, last successful publication, error, and retry state for Spoolman and Google.

### outbox_job

Durable external work item created in the same transaction as the canonical change.

### audit_event

Append-only record of actor, source, action, object, before/after JSON, correlation ID, and timestamp.

## Important relationships

```text
vendor 1---n filament_product 1---n spool
filament_product 1---n material_profile
printer 1---n material_profile
printer 1---n calibration_session
build_plate 1---n calibration_session
spool 1---n spool_measurement
spool 1---n spool_usage_event
spool 1---n nfc_tag
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

- chamber temperature
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
