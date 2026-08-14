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
- Use Fluidd to select the exact requested physical spool and confirm insertion without activating it before loading.
- Receive consumption through Moonraker and Spoolman.
- Warn when the selected spool is insufficient or materially incompatible where metadata permits.
- Pass the Cura managed material GUID into a Klipper preflight that bypasses changing only when the matching physical spool is already loaded.
- Unload at the removed filament's published nozzle temperature, clear active Spoolman state after physical unload, preheat/load at the selected filament's temperature, and activate the exact new ID only after physical load.
- Interact through the Spoolman API; direct Spoolman database access is prohibited.

### Manual first-release workflow

- Print a label containing the human spool ID and QR code.
- Search or scan the label in Filament Manager.
- Enter gross weight manually.
- Compute remaining filament from gross weight minus tare.
- Require confirmation when a measurement materially increases remaining mass.

### Cura material profiles

Store and export versioned profiles containing the approved Cura Material Settings catalog, including temperatures, flow, speeds, retraction, cooling, offsets, support angle, Cura Klipper Settings pressure advance/smooth time, density, and preferred build-plate side. Profiles are scoped by printer and nozzle diameter. Paired agents may report sanitized existing materials for explicit import into either a product-owned draft profile or a source-tracked draft template. A selected template import must be reviewed and published before authoritative takeover can proceed.

Compare two to four profile or template revisions visually using one baseline, difference-only settings, explicit cross-printer/nozzle warnings, and exact-profile outcome statistics. Template revisions have no print outcome statistics.

### Print inspection, history, and outcomes

- Inspect bounded Cura-generated G-code before print release using supported Moonraker file metadata/download APIs and retain the complete-file hash plus bounded evidence.
- Default inspection to warnings. Allow an Administrator to enable blocking for missing exact profile state, unavailable inspection, or supported mismatches.
- Import supported Moonraker live/history state and preserve immutable printer, physical spool, product, exact profile, plate, sliced metadata, actual usage, and M600 segment snapshots.
- Mark earlier history unresolved when exact material state cannot be reconstructed instead of guessing.
- Append outcome and quality-score revisions without rewriting prior assessments, and expose exact-profile success statistics.
- Keep persistent operational notifications with per-user read state for printer, spool, plate, job, and Cura deployment conditions.

### Build plates

- Seed physical `P1` through `P5` plates and discover later exact `P<number>` Side A or `P<number>b` Side B meshes.
- Group A/B sides under the shared physical P-number and map each side one-to-one to its same-named Klipper mesh.
- Preserve plate metadata and records when a saved mesh is temporarily absent.
- Align the active canonical physical plate and side to the loaded Moonraker mesh during synchronization.
- Record physical description/dimensions/condition/cleaning plus per-side surface material, smooth/textured finish, mesh calibration, and notes.
- Append cleaning and mesh events and calculate due state from configurable day and print-count thresholds.
- Associate a preferred plate side with each material profile.
- Preserve the existing mesh-selection prompt workflow.

### Calibration wizard

Guide a new filament through temperature, flow, pressure advance, retraction, dimensional size/hole calibration, overhang, and optional ironing tests. Dimensional calibration records X/Y/Z, hole, shaft, and wall measurements; applies only material-profile results and presents printer-geometry corrections for review without changing Klipper. Record selected results and publish a new immutable profile version.

### Future scale and NFC

- Accept a live load-cell stream from the dry box.
- Identify the loaded spool with NFC.
- Associate NFC UID with a spool record.
- Confirm physical NFC identity before setting the active spool through Moonraker/Spoolman.
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
4. A physically loaded and confirmed spool remains active in Moonraker/Spoolman and records print consumption during a Filament Manager restart.
5. Filament Manager reconciles the remaining mass into its canonical database.
6. A protected Google Sheet shows the updated inventory.
7. A user can record a manual gross weight and see the correction in Spoolman and the Sheet.
8. `P1` through `P5` appear initially; synchronizing `P6` creates physical P6 Side A, and `P6b` adds Side B without changing existing metadata.
9. A calibration session completes the seven-step workflow, calculates horizontal and hole expansion from recorded design/actual measurements, and produces a material-only Cura export containing the approved settings.
10. A Cura print with the matching spool already loaded reaches the existing `START_PRINT` unchanged; a mismatch pauses for exact-spool selection, unload, insertion confirmation, load, and truthful Spoolman transitions.
11. Print History preserves exact start-state evidence, M600 segments, inspection results, actual usage, and append-only outcome revisions; legacy records with unknowable state remain unresolved.
12. G-code inspection warns by default and pauses before physical spool selection when an Administrator enables blocking and inspection cannot prove a supported match.

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
