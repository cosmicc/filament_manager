# 03 - Canonical Data Model

## Modeling principles

- UUID technical keys, immutable human business IDs.
- Numeric types for mass, dimensions, density, flow, and money.
- Immutable event tables for measurements, usage, and calibration results.
- Versioned material profiles.
- Explicit projection state for Spoolman and Google.
- Soft archive rather than destructive delete for referenced records.

## Core entities

### vendor

Manufacturer identity and aliases.

### filament_product

A purchasable material definition: material, filler, finish, color, product/grade/hardness, diameter, tolerance, density, nominal weight, and vendor.

### spool

A physical spool with immutable `spool_code`, tare mass, purchase details, current expected remaining mass, status, location, Spoolman ID, and label data.

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

Printer identity, Moonraker endpoint, nozzle diameter, build volume, active plate, and integration state.

### build_plate

Physical plate record. Business IDs start with `P1` through `P5`. Fields include surface, vendor, dimensions, condition, Klipper mesh profile, last clean, last mesh calibration, and notes.

### material_profile

Versioned settings scoped to:

- filament product
- printer
- nozzle diameter
- optional layer-height range

Contains Cura and Klipper-related settings. Publishing creates a new immutable version rather than editing historical versions in place.

### calibration_session

Tracks a wizard run for one filament, printer, nozzle, and optional plate. Contains ordered step records and final profile version.

### calibration_step

One of temperature, flow, pressure advance, retraction, overhang, or ironing. Stores test parameters, test artifact, selected result, status, and notes.

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
- preferred build plate
- optional ironing fields

Store future Cura fields in `cura_extensions JSONB` with a schema version.

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
