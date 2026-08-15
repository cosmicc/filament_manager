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

## ADR-006: Distinct Spoolman service

**Decision:** deploy Spoolman as a distinct, independently configured service in the default combined stack, while retaining an optional standalone Spoolman stack.
**Reason:** a single default stack simplifies installation, while separate images, services, credentials, databases, and update policies preserve the important application boundaries.

**Consequences:**

- create the combined overlay automatically, or pre-create it for the optional separate-stack layout
- maintain separate credentials and database ownership in both layouts
- use service DNS in the combined stack and stack-prefixed DNS in the separate-stack layout
- use stable LAN DNS for Moonraker
- monitor and back up each application independently

## ADR-007: Combined deployment defaults

**Decision:** provide combined Compose for development and a combined remote-database Swarm stack for the default production installation. Retain separate production stacks as an operator-selected alternative.
**Reason:** one production stack matches the normal installation workflow, while the separate files preserve stronger rollout isolation where it is needed.

## ADR-008: PostgreSQL-backed jobs

**Decision:** use transactional outbox, row locking, and advisory locks rather than a separate broker for the first release.  
**Reason:** operational simplicity and transactional consistency.

## ADR-009: Scale as correction initially

**Decision:** treat accepted scale measurements as periodic physical corrections rather than a second consumption counter.  
**Reason:** prevents double-counting with Moonraker usage.

## ADR-010: Direct saves with immutable snapshots

**Decision:** operator edits save directly as current settings while material profile and template snapshots remain immutable internal history.
**Reason:** simple operation without sacrificing traceability, exact print state, or repeatable Cura generation.

## ADR-011: Environment-only Docker configuration

**Decision:** supply every deployer-specific Docker setting through scoped stack environment variables and support one Moonraker printer in the current contract. Do not require a mounted Filament Manager Docker config.

**Reason:** Portainer and command-line stack deployments need one visible configuration surface without separately creating and rotating Docker config objects.

**Consequences:**

- fixed invariants remain validated application defaults
- required deployment addresses and printer values fail during stack interpolation when omitted
- an empty Moonraker WebSocket variable derives the conventional endpoint from the HTTP base URL
- YAML files remain supported only for non-Docker development and compatibility
- authorized Docker and Portainer operators can inspect credential environment values during this transitional phase

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
