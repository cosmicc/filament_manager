# Filament Manager

Filament Manager is a self-hosted inventory and calibration application for physical filament spools, manual weight measurements, material profiles, build plates, and Klipper-based printers.

PostgreSQL is the canonical data store. A distinct Spoolman service remains the printer-facing usage service, while Google Sheets is an optional read-only publication target.

## Current capabilities

- Local Administrator, Operator, and Viewer accounts
- Canonical spool, filament, profile, printer, physical nozzle, solid/multicolor/rainbow color, and build-plate records with consistent grouped in-app editors
- Browser-based `.xlsx` workbook upload with automatic first-run printer/build-plate seeding and a conservative `Template ASA` takeover target for each configured printer/nozzle
- Directly saved and automatically favorited `Template <material type>` Cura entries whose complete effective values flow to linked filament profiles except for visibly highlighted sparse customizations, with exact inline validation and overlapping Cura aliases represented by one editor control
- Difference-only comparison of two to four current profiles/templates with printer/nozzle scope warnings and exact-profile print success rates
- Simple new-spool entry from filament amount plus optional full scale weight, automatic empty-spool calculation, correction editors, safe delete-or-archive behavior, and later gross-weight measurements with variance confirmation
- Immutable audit history and transactional projection outbox
- Immediate Spoolman REST projection plus one-minute complete convergence and usage reconciliation, including Filament Manager-owned free-text bucket locations, plus Moonraker control clients
- Exact completed-print counts per physical nozzle, build-plate side, and each distinct spool used by a print
- Guarded direct-Spoolman selection, automatic physical-spool drift repair, and P-number build-plate synchronization with a live saved-mesh selector, including manual Side B setup followed by exact mesh discovery (`P4`/`P4b`)
- Cura-to-Fluidd spool preflight with bounded G-code/profile inspection, optional fail-closed blocking, strict current exact-profile print choices, broader safe manual-load choices, and Spoolman updates only at completed unload/load boundaries
- Moonraker-backed print history with exact immutable material/plate/profile state, M600 segments, legacy import, G-code hashes, actual terminal-job spool deductions for every outcome, and append-only outcome scoring
- Automatic 5-minute Moonraker/Klipper printer information discovery with editable manual nozzle, hardware, and build-volume metadata
- Seven-step calibration workflow with X/Y/Z, hole, shaft, wall/flow, material-shrinkage, and non-applying printer-geometry recommendations
- Configurable build-plate cleaning/mesh reminders plus a persistent operator notification center
- Outbound-only Cura workstation agents with clearly identified fresh-install/upgrade paths and uninstallers, an explicit map-then-review source-to-existing-template takeover, direct intake of edits to known managed materials, and authoritative synchronization on Arch Linux and Windows 11 with backup, custom-profile material-key cleanup, corrupt-profile quarantine, drift repair, bundled-material hiding, and rollback
- Workshop Navy light and dark web interface with browser-local theme selection under Settings and the running version in the application shell
- Health, readiness, and Prometheus metrics endpoints
- A dedicated Diagnostics page with connection, synchronization, worker, queue, recent-error, running/latest-version, read-only recovery-validation, safe projection-rebuild controls, and a sanitized plain-text log download

## Start locally

See [INSTALL.md](INSTALL.md) for prerequisites, deployment variables, automatic database upgrades, first-user bootstrap, and Docker Compose instructions.

The root [docker-stack.yml](docker-stack.yml) deploys Filament Manager, its worker, and Spoolman together against a remote PostgreSQL server. All deployer-supplied settings for the current one-printer Docker deployment come from stack variables; no separate application Docker config is required. Independent application stack examples remain under `docker/` for operators who need separate lifecycles.

The current remote-database contract explicitly disables PostgreSQL TLS and therefore requires an operator-managed isolated network restricted to the approved Swarm nodes.

The newest CI-passing `main` image is published as `ghcr.io/cosmicc/filament-manager:latest` for AMD64 and ARM64. Web and worker startup automatically applies pending Filament Manager Alembic migrations under a PostgreSQL advisory lock. The web image health check uses the hostname from `FILAMENT_MANAGER_BASE_URL`; worker services disable that HTTP-only check. Production deployments should pin the immutable `sha-<commit>` tag or image digest from the successful package workflow.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Testing](docs/TESTING.md)
- [Operations](docs/OPERATIONS.md)
- [Cura workstation agent](docs/CURA_WORKSTATION_AGENT.md)
- [Cura Material Settings plugin selection list](docs/CURA_MATERIAL_PRINT_SETTINGS.txt)
- [Printing workflow and complete macro contract](docs/PRINTING_WORKFLOW.md)
- [Source specifications](docs/specification/01_PRODUCT_REQUIREMENTS.md)
