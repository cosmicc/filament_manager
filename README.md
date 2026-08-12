# Filament Manager

Filament Manager is a self-hosted inventory and calibration application for physical filament spools, manual weight measurements, material profiles, build plates, and Klipper-based printers.

PostgreSQL is the canonical data store. A distinct Spoolman service remains the printer-facing usage service, while Google Sheets is an optional read-only publication target.

## Current capabilities

- Local Administrator, Operator, and Viewer accounts
- Canonical spool, filament, profile, printer, remembered color, and build-plate records with in-app editors
- Browser-based `.xlsx` workbook upload and Printers page setup actions with first-run printer and build-plate seeding
- Versioned printer/nozzle material templates that start each new product-specific profile
- Manual gross-weight measurements with variance confirmation
- Immutable audit history and transactional projection outbox
- Immediate Spoolman REST projection plus one-minute complete convergence and usage reconciliation, including Filament Manager-owned free-text bucket locations, plus Moonraker control clients
- P1-P5 initial physical build plates, Side A/Side B Moonraker mesh discovery (`P4`/`P4b`), and a seven-step calibration workflow with dimensional and hole compensation
- Moonraker/Klipper printer information discovery with editable nozzle, kinematics, hardware, and build-volume metadata
- Outbound-only Cura workstation agents for importing materials and keeping an authoritative Filament Manager material library synchronized on Arch Linux and Windows 11, with backup, drift repair, bundled-material hiding, and rollback
- Workshop Navy light and dark web interface
- Health, readiness, and Prometheus metrics endpoints

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
- [Source specifications](docs/specification/01_PRODUCT_REQUIREMENTS.md)
