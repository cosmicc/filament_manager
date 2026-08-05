# 23 - Architecture Decision Records

## ADR-001: Canonical PostgreSQL database

**Decision:** Filament Manager PostgreSQL is the canonical source of truth.  
**Reason:** auditability, constraints, history, and deterministic rebuilding of projections.

## ADR-002: Google Sheet is read-only

**Decision:** publish database-to-Sheet only after migration.  
**Reason:** avoids multi-master conflicts and preserves a familiar view.

## ADR-003: Reuse Spoolman

**Decision:** integrate with upstream Spoolman rather than recreating its Moonraker/Fluidd ecosystem.  
**Reason:** proven interoperability, label support, API, and active-spool workflow.

## ADR-004: Separate databases and roles

**Decision:** use `filament_manager` and `spoolman` as separate databases on the same central PostgreSQL server.  
**Reason:** migration isolation, least privilege, independent backup/restore, and reduced coupling.

## ADR-005: API integration only

**Decision:** Filament Manager uses Spoolman's REST/WebSocket interfaces and never directly reads or writes Spoolman tables.  
**Reason:** protects against upstream schema and migration changes.

## ADR-006: Standalone Spoolman Swarm stack

**Decision:** deploy Spoolman as stack `spoolman` and Filament Manager as stack `filament-manager`.  
**Reason:** independent upgrades, failure isolation, continuous Moonraker usage tracking, and future multi-printer reuse.

**Consequences:**

- create an external overlay network before deployment
- maintain separate stack files and secrets
- use stack-prefixed internal DNS for Filament Manager-to-Spoolman traffic
- use stable LAN DNS for Moonraker
- monitor and back up each application independently

## ADR-007: Combined Compose is development-only

**Decision:** provide a combined Compose file for developer convenience, not production.  
**Reason:** local testing benefits from one command, while production reliability requires independent lifecycle boundaries.

## ADR-008: PostgreSQL-backed jobs

**Decision:** use transactional outbox, row locking, and advisory locks rather than a separate broker for the first release.  
**Reason:** operational simplicity and transactional consistency.

## ADR-009: Scale as correction initially

**Decision:** treat accepted scale measurements as periodic physical corrections rather than a second consumption counter.  
**Reason:** prevents double-counting with Moonraker usage.

## ADR-010: Version profiles

**Decision:** published material profiles are immutable versions.  
**Reason:** traceability and repeatable Cura generation.

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
