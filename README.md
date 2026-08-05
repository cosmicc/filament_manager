# Filament Manager

Filament Manager is a self-hosted inventory and calibration application for physical filament spools, manual weight measurements, material profiles, build plates, and Klipper-based printers.

PostgreSQL is the canonical data store. A separately operated Spoolman stack remains the printer-facing usage service, while Google Sheets is an optional read-only publication target.

## Current capabilities

- Local Administrator, Operator, and Viewer accounts
- Canonical spool, filament, profile, printer, and build-plate records
- Workbook dry-run import and duplicate/validation reporting
- Manual gross-weight measurements with variance confirmation
- Immutable audit history and transactional projection outbox
- Spoolman REST projection and periodic reconciliation plus Moonraker control clients
- P1-P5 build plates and six-step calibration workflow
- Outbound-only Cura workstation agents for automated Arch Linux and Windows 11 profile deployment, backup, and rollback
- Workshop Navy light and dark web interface
- Health, readiness, and Prometheus metrics endpoints

## Start locally

See [INSTALL.md](INSTALL.md) for prerequisites, secret creation, database migration, first-user bootstrap, and Docker Compose instructions.

Production deployment examples are under `docker/`; the two Swarm stacks are intentionally independent.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Testing](docs/TESTING.md)
- [Operations](docs/OPERATIONS.md)
- [Cura workstation agent](docs/CURA_WORKSTATION_AGENT.md)
- [Source specifications](docs/specification/01_PRODUCT_REQUIREMENTS.md)
