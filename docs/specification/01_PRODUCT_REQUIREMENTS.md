# 01 - Product Requirements

## Product objective

Filament Manager provides one trusted inventory for physical filament spools, measured remaining mass, calibrated print settings, build-plate compatibility, and printer usage. It integrates with Klipper, Moonraker, Fluidd, and a separately operated Spoolman service.

## Primary users

- Administrator who deploys and operates the services
- Printer operator who loads spools, selects build plates, records weights, and runs calibrations
- Viewer who uses the Google Sheet to inspect current inventory and settings
- Future hardware adapters for scale and NFC data

## Functional requirements

### Inventory

- Import the current workbook once with a dry-run report.
- Maintain vendors, filament products, physical spools, purchase data, costs, labels, tare weights, current mass, and notes.
- Preserve existing human `Spool ID` values.
- Record every inventory mutation in an audit log.

### Source of truth

- Store canonical data in the central `filament_manager` PostgreSQL database.
- Use Spoolman as the printer-facing operational projection.
- Publish a read-only Google Sheet automatically.
- Recreate projections from PostgreSQL after failure.

### Production deployment

- Provide one default Docker Swarm stack containing Spoolman, Filament Manager, and the Filament Manager worker.
- Keep optional independent Spoolman and Filament Manager stack files for environments that require separate rollout and rollback lifecycles.
- Connect the services through a private `filament-services` overlay network.
- Use the same central PostgreSQL server but separate databases, owners, passwords, migrations, and backup objects.
- Keep image tags independently configurable and preserve service-level restarts and health monitoring in the combined stack.
- Supply every deployer-specific Docker setting through stack environment variables without requiring a mounted application configuration object.
- Support one Moonraker printer in the current Docker variable contract, with an optional explicit WebSocket URL.
- Provide a combined Compose file for local development and integration testing.

### Spoolman and printer integration

- Configure Spoolman to use the central PostgreSQL server.
- Allow Fluidd to select or scan an active spool.
- Receive consumption through Moonraker and Spoolman.
- Warn when the selected spool is insufficient or materially incompatible where metadata permits.
- Interact through the Spoolman API; direct Spoolman database access is prohibited.

### Manual first-release workflow

- Print a label containing the human spool ID and QR code.
- Search or scan the label in Filament Manager.
- Enter gross weight manually.
- Compute remaining filament from gross weight minus tare.
- Require confirmation when a measurement materially increases remaining mass.

### Cura material profiles

Store and export versioned profiles containing chamber temperature, extruder temperature, bed temperature, flow, print speeds, retraction distance and speed, cooling state and range, support overhang angle, maximum tree-support branch angle, pressure advance, density, preferred build plate, and future extension fields. Profiles are scoped by printer and nozzle diameter.

### Build plates

- Track `P1` through `P5`.
- Map each plate to its Klipper bed-mesh profile.
- Record surface, dimensions, condition, last cleaning, last mesh calibration, and material suitability.
- Associate a preferred plate with each material profile.
- Preserve the existing mesh-selection prompt workflow.

### Calibration wizard

Guide a new filament through temperature, flow, pressure advance, retraction, overhang, and optional ironing tests. Record selected results and publish a new immutable profile version.

### Future scale and NFC

- Accept a live load-cell stream from the dry box.
- Identify the loaded spool with NFC.
- Associate NFC UID with a spool record.
- Set the active spool through Moonraker/Spoolman.
- Keep manual fallback available.

## Non-functional requirements

- Printing and Spoolman usage tracking continue if Filament Manager or Google is unavailable.
- Filament Manager and Spoolman runtime failures are isolated by service and database boundaries; operators requiring independent stack rollouts use the separate stack files.
- Database writes are transactional.
- External projections are eventually consistent and rebuildable.
- External operations are idempotent and retryable.
- Support amd64 and arm64 images.
- Provide health, readiness, and metrics endpoints.
- Use least-privilege credentials, scoped environment delivery for the current deployment phase, and masked application configuration.
- Preserve measurement and calibration history.

## MVP acceptance criteria

1. Workbook imports into PostgreSQL with no lost fields.
2. Spoolman connects to its dedicated database on the central PostgreSQL server.
3. Filament Manager connects to Spoolman across the stack overlay network.
4. A spool selected in Fluidd records print consumption even during a Filament Manager restart.
5. Filament Manager reconciles the remaining mass into its canonical database.
6. A protected Google Sheet shows the updated inventory.
7. A user can record a manual gross weight and see the correction in Spoolman and the Sheet.
8. `P1` through `P5` appear as build plates with matching mesh names.
9. A calibration session completes the six-step workflow and produces a Cura profile export.

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
