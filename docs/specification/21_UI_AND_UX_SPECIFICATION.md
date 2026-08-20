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
- Nozzles
- Labels
- Integrations
- Cura Workstations
- Diagnostics
- Activity/Audit
- Settings

## Dashboard

Show:

- active spool and remaining mass
- active build plate and mesh
- current print and usage status
- low/empty inventory
- calibration tasks
- last accepted measurement

The Dashboard does not duplicate Diagnostics. Quick Actions spans the available width in a horizontal layout and includes weighing a spool, printing labels, loading/selecting filament, and adding filament.

## Spool detail

- label/QR
- current effective, measured, and expected mass
- tare and measurement history
- usage history
- product/profile
- free-text storage bucket/location with edit and clear actions
- Spoolman projection status
- manual weigh action
- full setup correction plus delete-or-archive action
- **Load spool** action that queues the confirmed Fluidd workflow without changing the active indicator early
- NFC association later

## Calibration wizard UX

Use a persistent stepper with the exact seven steps. Each step has instructions, test settings, file/job link, result fields, notes, and “repeat” action. Size and Hole Calibration collects raw X/Y/Z, hole, shaft, and wall dimensions; shows Cura expansion, flow, shrinkage, and non-applying printer-geometry recommendations; and warns about directional divergence. Show downstream invalidation before allowing an earlier result to change. After mandatory steps finish, display every derived Cura recommendation with actions to apply it to the filament profile or, after warning plus exact-name confirmation, the latest linked template. Confirm deletion of an unapplied session and never offer deletion for applied history.

## Build plate UX

Full-width summaries begin with physical P1-P5 and naturally order later discovered plates. Each physical card uses its sanitized uploaded picture in the plate icon when present and shows its description, manufacturer/product, shape/dimensions, magnetic/flexible state, condition/status, preferred materials, temperature limit, cleaning state, configurable day/print reminder thresholds, and nested Side A/Side B panels with exact mesh, surface material, smooth/textured finish, mesh availability/check/calibration time, notes, and completed-print count. Cleaning and mesh actions append maintenance events. The active side is visually explicit and may be cleared only through the physical Moonraker workflow. Operators may add the one Side B record; it remains unavailable until its exact mesh is discovered. State synchronizes automatically every 15 seconds.

Before authoritative takeover, Cura Workstations opens a dedicated two-stage dialog listing every sanitized Cura material file and saved print-profile candidate reported by a paired agent, including named zero-literal and expression-only candidates. Each row distinguishes its source type, shows tracked-setting count, and provides a selector containing existing active templates plus **Do not import**; print profiles also show matched machine/quality metadata and omitted-expression count. Each source and template may be used once. **Review takeover** shows all mappings and the ignored count, **Back to mappings** restores the selectors, and **Complete takeover** supplies one confirmation for the atomic import, inheritance cascade, management transition, and synchronization queue. The Templates page links directly to this surface. The workflow never modifies workstation files before confirmation.

The Templates page creates and directly edits complete material settings named `Template <material type>` with brand `Template`. Material Profiles and Templates expose one shared read-only comparator: choose two to four current profiles/templates, with the first as the baseline. The result contains only settings whose canonical values differ, treats equivalent decimal representations as equal, displays all scopes, and shows exact-profile outcome rates; template statistics are N/A and samples below five are labeled low. Any printer or nozzle pairing is allowed, but a prominent warning identifies each mismatched scope dimension. The Filaments page requires a current template, explains that its linked product profile stores sparse customizations, renders arbitrary shared solid colors, product-specific one/two/three-sample multicolor palettes, and fixed Rainbow color, and links each product to a complete correction/settings editor. Opening the color control shows known colors again while allowing a new typed name. A filament card uses three identity lines: blue vendor; bold material type, color name, and optional display name; then smaller filler and finish separated by `/`. Every palette mode uses the same physical spool silhouette. Color remains editable until retained use exists. Product editing resolves the linked template identity to its current direct-save snapshot, shows it first, and lists other active templates with matching material, printer, and nozzle scope. Profile details show the linked template, inherited/customized count, and template values beside each setting. Settings use Cura-like named groups without an advanced catch-all; Retraction Retract Speed and Retraction Prime Speed are independent, Cooling contains the five requested fan/layer-time/minimum-speed values, and hidden Initial Fan Speed always saves as zero. An edit that differs from its inherited value highlights immediately. Saving a template immediately updates every linked profile except explicitly customized keys; saving any known profile/template in Filament Manager or Cura queues synchronization automatically. Profile Cura settings download as JSON attachments. The Spools page shows completed prints, creates physical spools from filament-only amount plus optional full scale weight with an inferred-tare preview, identifies the associated printer, provides full setup correction/delete-or-archive actions, lets Operators edit or clear free-text bucket locations, and offers a physical **Unload** action that clears Spoolman only after completed motion. Its **Load spool** action reports that Fluidd will request physical confirmation, automatically follows the unload/insert/load workflow when another spool is present, and keeps the current active spool visible until that load finishes. New materials can be added only in Filament Manager.

Manual Fluidd load commands show the live non-empty projected-spool catalog without a separately staged target field or current exact-profile requirement. Each choice still requires a safe printer/nozzle temperature from its newest exact profile or linked template. A direct non-null Spoolman selection becomes a guarded confirmation and remains non-canonical until already-loaded confirmation or physical load completion. `SELECT_BUILD_PLATE` without a parameter shows the current valid exact P-number meshes reported by Klipper.

## Nozzles and diagnostics

Nozzles shows editable unique physical code, diameter, construction material, lifecycle state, installed printer, completed prints, total filament use, and append-only install/remove history. The currently installed nozzle card has a subtle semantic highlight in addition to its status label. Installing a nozzle replaces no record silently and one printer has at most one installed nozzle.

Diagnostics shows the running application version and cached newest non-draft GitHub release, then groups connection, synchronization, worker, and operational information; actionable queue depth and job actions; bounded recent errors with a **Download log** text action; persisted read-only validation results; and an Administrator-only safe projection rebuild. Superseded recurring failures remain historical but do not inflate actionable queue debt. The download comes from the authenticated server overview and uses the same bounded sanitization as the screen. Dashboard, Printers, Integrations, and Cura Workstations do not duplicate detailed operational status.

## Print history, notifications, and accounts

Print History distinguishes exact-state records from unresolved legacy imports. Detail shows immutable sliced and actual metadata, complete-file hash, G-code inspection findings, spool/profile/plate snapshots, M600 segments, and retained outcome history. Operators can directly rate or update a finished print as failed, acceptable, successful, or excellent and add bounded defect tags and notes; earlier assessments remain immutable without exposing revision controls.

The application shell polls persistent notifications, shows unread severity and count, links to the affected workflow, and supports individual or bulk read actions. It also shows the build version, one icon-labelled Logout action without a username/account pill, and direction-only collapse/restore chevrons. Settings offers exactly three light and five dark GUI color profiles. Activity cards use green for success, red for error, yellow for warning, and distinct semantic informational colors while retaining text/icon status cues. Integrations is a concise configuration/ownership page without an Operational Information card or top Diagnostics button. Settings contains one **Account** editor for username, display name, and password and no Security Defaults card. The empty-database `admin` / `admin` account sees only the forced password-replacement screen until changed.

Desktop data tables transform into compact action-preserving cards below the mobile breakpoint, including inventory, profiles, prints, activity, integration jobs, labels, and Cura synchronization operations.

The Printers page shows sanitized discovered Klipper/Moonraker versions, hostname, kinematics, nozzle, and build volume alongside editable hardware metadata. Information synchronizes automatically every 5 minutes, while operational state refreshes every 15 seconds. Only Administrators may edit printer information, and no connection address or secret appears in the browser.

## Editing pattern

Record creation and editing uses one shared accessible modal shell with a clear title and description, visible named option groups, a scrollable body, and consistent Cancel/Save footer actions. Initial focus is established once when the modal opens; controlled-field rerenders must never return focus to the close control while an operator types. Do not hide editable fields in fold-down sections. Persistent multi-step workflows such as calibration and workbook import remain in-page but use the same visible grouped-section treatment.

Displayed values never expose storage-scale padding. Temperatures, flow/fan, angles, and speeds use whole numbers; nozzles and ordinary dimensions use at most one decimal; tolerance, density, pressure advance, layer/line dimensions, and calibration evidence use at most two. No user-facing value uses three or more decimal places.

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
