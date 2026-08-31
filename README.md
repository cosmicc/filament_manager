# Filament Manager

Filament Manager is a self-hosted inventory and calibration application for physical filament spools, manual weight measurements, material profiles, build plates, and Klipper-based printers.

PostgreSQL is the canonical data store. A distinct Spoolman service remains the printer-facing usage service, while Google Sheets is an optional read-only publication target.

## Current capabilities

- One editable local Administrator account, created as `admin` / `admin` on an empty installation with a mandatory first-login password change, plus a thirty-day absolute browser session and rolling seven-day idle window
- Canonical spool, filament, exact printer-owned physical-nozzle print settings, printer, editable per-printer nozzle codes, per-product multicolor/rainbow palettes, and compact responsive build-plate records with independently remembered List, Cards, and Detailed catalog views and complete selected-item actions
- Browser-based `.xlsx` workbook upload with automatic first-run printer/build-plate seeding and a conservative `Template ASA` takeover target for each configured printer/nozzle
- A Filaments workspace with separate Catalog and Print settings views, concise identities that omit implied `None` filler and `Standard` finish labels, useful tolerance/printing-temperature card facts, multiple current printer/nozzle settings per physical filament, and exact-scope editing, comparison, Cura JSON export, inheritance, density updates, and duplication
- Directly saved and automatically favorited `Template <material type>` Cura entries with clickable List/Cards/Detailed records, edit-page JSON export and confirmed history-preserving deletion, installed-nozzle defaults, editable printer/nozzle scope, confirmed create/overwrite import, and complete effective values that flow only to current exact scopes that inherit them, except for visibly highlighted sparse customizations, with template-only speed/smooth-time/acceleration controls, profile-editable cooling/pressure-advance/ironing values, a visible per-blank-field copy selector using any populated active template, refreshed-before-edit concurrency protection, centered exact inline validation with field-by-field reasons and safe diagnostic references, one primary Flow, separate regular and initial-layer Build Plate temperatures, and overlapping retract/fan aliases represented by one editor control
- Difference-only comparison of two to four current profiles/templates with printer/nozzle scope warnings and exact-profile print success rates
- Simple new-spool entry from purchased filament weight plus optional full scale weight, automatic empty-spool calculation, purchase cost and cost-per-gram display, correction editors, safe delete-or-archive behavior, and later gross-weight measurements with variance confirmation
- Color-aware QR spool labels with a centered solid, multicolor, or rainbow spool icon and high error correction for reliable scanning
- Immutable audit history and a transactional Projection Queue with bounded retries, live retry timing, recovered-history supersession, and coalesced Spoolman weight corrections
- Immediate Spoolman REST projection plus one-minute complete convergence and usage reconciliation, including Filament Manager-owned free-text bucket locations, plus Moonraker control clients with active-spool polling and retry inside one minute
- Exact current and completed-print records with an all-printers/default or exact-printer filter, subtle semantic outcome backgrounds, server-side 10/25/50/100 pagination, retryable request failures kept distinct from a genuine empty history, exact Moonraker terminal outcomes, nozzle/build-plate/spool attribution, sanitized stored G-code thumbnails, actual-versus-estimated statistics, immutable captured filament cost, useful bounded Moonraker details, and authenticated links to matching Moonraker-timelapse videos
- Guarded direct-Spoolman selection, automatic physical-spool drift repair, and P-number build-plate synchronization with a live saved-mesh selector, one-click next-P-number creation, obvious missing-heatmap warnings, and manual Side B setup followed by exact mesh discovery (`P4`/`P4b`)
- Cura-to-Fluidd spool preflight with bounded G-code/profile inspection, retryable fail-closed blocking decisions, a thirty-second bounded virtual-SD release retry with explicit recovery actions, orphan-safe cancellation across printer start and build-plate selection, strict current exact-profile print choices, broader safe manual-load choices, and Spoolman updates only at completed unload/load boundaries
- Moonraker-backed print history with exact immutable material/plate/profile and segment cost state, M600 segments, legacy import, G-code hashes, actual terminal-job spool deductions for every outcome, and append-only outcome scoring
- Automatic 5-minute Moonraker/Klipper printer information discovery with editable manual nozzle, hardware, and build-volume metadata
- A 10-second live Dashboard snapshot led by the full-width printer status card with three inventory value cards directly beneath it, plus safe Moonraker/Klipper availability, active spool and plate, print state and expanded progress, compact in-print nozzle/bed/chamber temperatures, current thumbnail, elapsed/estimated time, and filament use and cost so far
- Seven-step calibration workflow with X/Y/Z, hole, shaft, wall/flow, material-shrinkage, suggested Cura settings, direct filament-profile application, confirmed linked-template application, and safe in-progress deletion
- Uploaded, sanitized build-plate pictures, configurable cleaning/mesh reminders, and a persistent color-coded operator activity/notification center with outside-click dismissal
- Outbound-only Cura workstation agents with interactive Windows pairing, per-user PATH/startup registration, clearly identified fresh-install/upgrade paths and uninstallers, stable managed material identities with meaningful filler-qualified product labels that omit missing or `None` filler values, safe legacy extruder-stack repair, automatic managed-material start/end print boundaries with distinct initial and regular bed temperatures, automatic required Material Settings enablement without removing unrelated Cura choices, bidirectional in-Cura managed-value saving without polluting Cura-only quality profiles, exact expected/exposed verification, required-plugin version/readiness status, currency-safe product cost estimates, recurring exact linked-extruder nozzle verification and alignment, authoritative synchronization, fifteen rotating automatic Cura recovery points plus explicitly retained named points—listed before separate historical request failures and reusable across workstations with an exact Cura-version match and explicit confirmation—on Arch Linux and Windows 11
- Three light and nine dark browser-local color profiles under Settings, with the running version in the application shell
- Health, readiness, and Prometheus metrics endpoints
- Optional privacy-sanitized Bugsnag browser/server/worker error reporting and browser performance monitoring, disabled by default
- A dedicated Diagnostics page with connection, synchronization, worker, actionable queue summaries, per-job-type failure causes, one/seven/thirty-day recent-error filtering, complete timestamped validation results, current-versus-historical error distinction, per-installation Cura material-setting verification, running/latest-version, safe projection-rebuild controls, and a matching sanitized plain-text log download
- Configurable compressed canonical PostgreSQL snapshots with ten-backup automatic retention by default, PostgreSQL 18 client compatibility, live-print deferral with stale interrupted-print recovery, bounded safe failure guidance and backoff, trusted ZIP download/import, and a confirmed stopped-service catastrophic restore workflow

## Start locally

See [INSTALL.md](INSTALL.md) for prerequisites, deployment variables, automatic database upgrades, first-login credentials, and Docker Compose instructions.

The root [docker-stack.yml](docker-stack.yml) deploys Filament Manager, its worker, and Spoolman together against a remote PostgreSQL server. All deployer-supplied settings for the current one-printer Docker deployment come from stack variables; no separate application Docker config is required. Independent application stack examples remain under `docker/` for operators who need separate lifecycles.

The current remote-database contract explicitly disables PostgreSQL TLS and therefore requires an operator-managed isolated network restricted to the approved Swarm nodes.

The newest CI-passing `main` image is published as `ghcr.io/cosmicc/filament-manager:latest` for AMD64 and ARM64. Web and worker startup automatically applies pending Filament Manager Alembic migrations under a PostgreSQL advisory lock. The web image health check uses the hostname from `FILAMENT_MANAGER_BASE_URL`; worker services disable that HTTP-only check. Production deployments should pin the immutable `sha-<commit>` tag or image digest from the successful package workflow.

## Documentation

- [Full-color 128 x 128 app icon for notification services](frontend/public/assets/filament-manager-icon-128.png)
- [GUI color-profile palette reference](docs/design/theme-palettes.svg)
- [Architecture](docs/ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Testing](docs/TESTING.md)
- [Operations](docs/OPERATIONS.md)
- [Cura workstation agent](docs/CURA_WORKSTATION_AGENT.md)
- [Cura Material Settings plugin selection list](docs/CURA_MATERIAL_PRINT_SETTINGS.txt)
- [Printing workflow and complete macro contract](docs/PRINTING_WORKFLOW.md)
- [Source specifications](docs/specification/01_PRODUCT_REQUIREMENTS.md)
