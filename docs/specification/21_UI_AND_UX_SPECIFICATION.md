# 21 - UI and UX Specification

## Navigation

- Dashboard
- Spools
- Filaments
- Profiles
- Print History
- Templates
- Calibration Wizard
- Build Plates
- Printers
- Labels
- Integrations
- Activity/Audit
- Settings

## Dashboard

Show:

- active spool and remaining mass
- active build plate and mesh
- current print and usage status
- low/empty inventory
- calibration tasks
- Spoolman/Moonraker/Google health
- last accepted measurement

## Spool detail

- label/QR
- current effective, measured, and expected mass
- tare and measurement history
- usage history
- product/profile
- free-text storage bucket/location with edit and clear actions
- Spoolman projection status
- manual weigh action
- **Load spool** action that queues the confirmed Fluidd workflow without changing the active indicator early
- NFC association later

## Calibration wizard UX

Use a persistent stepper with the exact seven steps. Each step has instructions, test settings, file/job link, result fields, notes, and “repeat” action. Size and Hole Calibration collects raw X/Y/Z, hole, shaft, and wall dimensions; shows Cura expansion, flow, shrinkage, and non-applying printer-geometry recommendations; and warns about directional divergence. Show downstream invalidation before allowing an earlier result to change.

## Build plate UX

Full-width summaries begin with physical P1-P5 and naturally order later discovered plates. Each physical card shows its description, manufacturer/product, shape/dimensions, magnetic/flexible state, condition/status, preferred materials, temperature limit, cleaning state, configurable day/print reminder thresholds, and nested Side A/Side B panels with exact mesh, surface material, smooth/textured finish, mesh availability/check/calibration time, and notes. Cleaning and mesh actions append maintenance events. The active side is visually explicit and may be cleared only through the physical Moonraker workflow. State synchronizes automatically every 15 seconds; Operators may edit metadata and select available sides without directly creating integration-controlled records.

The Material Profiles page lists sanitized existing Cura material candidates reported by paired agents. Import requires explicit canonical filament, printer/nozzle, and optional preferred-side mapping and creates a draft without modifying the workstation file.

The Templates page creates complete material settings revisions named `Template <material type>` and publishes them per printer/nozzle. Material Profiles and Templates expose one shared read-only comparator: choose two to four profile or saved template revisions, with the first as the baseline. The result contains only settings whose canonical values differ, treats equivalent decimal representations as equal, displays all scopes, and shows exact-profile outcome rates; template statistics are N/A and samples below five are labeled low. Any printer or nozzle pairing is allowed, but a prominent warning identifies each mismatched scope dimension. The Filaments page requires a published template in its routine creation flow, explains that a directly linked product draft stores sparse overrides, renders real remembered color samples, and links each product to a complete detail/settings editor. Profile details show the exact base revision, inherited/customized count, template values beside each setting, and one per-filament confirmation flow for a newer published template. A color sample change states that it applies to all matching existing and future color names. The Spools page creates physical spools from canonical products, identifies the associated printer, lets Operators edit or clear free-text bucket locations, and offers a physical **Unload** action that clears Spoolman only after completed motion. Its **Load spool** action reports that Fluidd will request physical confirmation and keeps the current active spool visible until that load finishes. Cura Workstations shows unmanaged material count, groups every reported material under **Preserve before takeover**, imports selected materials as source-tracked draft templates, links drafts to review/publication, blocks takeover until selected imports are active and published, requires an explicit replacement warning before authoritative takeover of the remaining user library, and explains that edits to known managed entries return as drafts while new Cura-created materials are ignored.

## Print history, notifications, and accounts

Print History distinguishes exact-state records from unresolved legacy imports. Detail shows immutable sliced and actual metadata, complete-file hash, G-code inspection findings, spool/profile/plate snapshots, M600 segments, and append-only outcome revisions. Operators can rate a finished print as failed, acceptable, successful, or excellent and add bounded defect tags and notes.

The application shell polls persistent notifications, shows unread severity and count, links to the affected workflow, and supports individual or bulk read actions. A new or reset account sees only the forced password-replacement screen until the temporary password is changed.

Desktop data tables transform into compact action-preserving cards below the mobile breakpoint, including inventory, profiles, prints, activity, integration jobs, labels, and Cura deployments.

The Printers page shows sanitized discovered Klipper/Moonraker versions, hostname, kinematics, nozzle, and build volume alongside editable hardware metadata. Information synchronizes automatically every 5 minutes, while operational state refreshes every 15 seconds. Only Administrators may edit printer information, and no connection address or secret appears in the browser.

## Editing pattern

Record creation and editing uses one shared accessible modal shell with a clear title and description, visible named option groups, a scrollable body, and consistent Cancel/Save footer actions. Do not hide editable fields in fold-down sections. Persistent multi-step workflows such as calibration and workbook import remain in-page but use the same visible grouped-section treatment.

## Google status

Display publication time, rows updated, drift warnings, and rebuild action. Never suggest editing the Sheet as a normal workflow.

## Manual weight UX

Large numeric input, selected spool identity, tare, computed remaining mass, variance, and confirmation for suspicious values. Optimize for mobile use near the printer.

## Accessibility

Keyboard navigation, semantic labels, adequate contrast, non-color status indicators, and clear error recovery.

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
