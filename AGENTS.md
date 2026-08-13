# Filament Manager Agent Guide

## Mission

Build and maintain Filament Manager, a security-focused, self-hosted application for filament inventory, measurements, material profiles, calibration, build plates, and supported Klipper ecosystem integration.

The product name is **Filament Manager**. Do not introduce the former project name in code, documentation, configuration, deployment objects, or user-facing copy.

## Authority and boundaries

1. The `filament_manager` PostgreSQL database is canonical.
2. Standalone Spoolman is the printer-facing operational projection and usage service.
3. Google Sheets is a one-way, read-only publication target.
4. The supplied workbook is an initial-import fixture only.
5. Filament Manager integrates with Spoolman through its supported REST API and periodic reconciliation; direct database access is prohibited.
6. The default production deployment uses the root `docker-stack.yml` to run Spoolman and Filament Manager together while keeping their remote PostgreSQL databases, roles, credentials, migrations, and backups separate. The independent stack files under `docker/` remain available when operational isolation is required.
7. Cura files are changed only by the outbound-only per-user workstation agent under `workstation-agent/`; the server never reaches into a workstation or listens on an agent port. After explicit takeover of a workstation with existing user materials, Filament Manager owns the complete user material library, deploys the latest published templates under the exact `Template <material type>` name and `Template` brand plus every published product profile, removes stale user material files after backup, and installs its visibility plugin so bundled Cura materials are hidden. The Cura Material Settings plugin exposes stored values, and the Cura Klipper Settings plugin owns pressure advance and smooth time; never patch machine start G-code or create quality-change profiles.
   Re-running either supported workstation installer is an in-place upgrade: preserve pairing credentials and Cura backup/state data, replace only managed code and service/task definitions, and restart only an agent that was already running.
   Before authoritative takeover, an Administrator may preserve selected reported Cura materials as source-tracked draft templates. Takeover must remain blocked until every selected import is active and has a published revision.
   After takeover, the agent may report bounded approved setting changes only for known deterministic managed material GUIDs. Each semantic change creates one idempotent draft template or profile revision for review; never publish automatically and never admit a new Cura-created material into canonical state.
8. Docker deployments are environment-only: every deployer-supplied application setting and credential comes from scoped stack variables, with no mounted application Docker config and no Docker secrets. The current variable contract supports exactly one Moonraker printer. Treat credential variables as a transitional risk, restrict manager and Portainer access, keep populated `.env` files untracked with mode `0600`, and never log or render these values.
9. The container image health check is web-specific: it probes loopback with the public hostname from `FILAMENT_MANAGER_BASE_URL` so trusted-host validation remains enforced. Every worker or one-shot service must disable this inherited HTTP health check.
10. Successful CI for a `main` push publishes the Filament Manager container for AMD64 and ARM64 with `latest` and immutable `sha-<commit>` tags. Treat `latest` as a testing convenience; production deployments pin an immutable SHA tag or digest. Image publication does not authorize a Git tag or GitHub Release.
11. Remote PostgreSQL connections use `filament_user` and `spoolman_user` with TLS explicitly disabled on the operator-managed isolated database network. Preserve SCRAM authentication, narrow firewall and `pg_hba.conf` rules, and separate database ownership; this non-SSL contract is unsafe on shared or untrusted networks.
12. The container entry point automatically upgrades the Filament Manager schema before starting web or worker commands. Concurrent tasks coordinate with one bounded PostgreSQL session advisory lock; a failed or timed-out migration must stop startup. Keep the opt-out only for controlled recovery.
13. Filament Manager owns spool locations after initial adoption. A legacy spool with no canonical location may import one existing bounded free-text Spoolman location; every local edit, including clearing the field, makes the canonical value authoritative and reconciliation repairs later remote drift.
14. `filament_colors` owns the case-insensitive mapping from a human color name to its six-digit screen sample. A sample change updates every matching product mirror and queues their Spoolman projections; never treat per-product color hex as independent state.
15. Printer information synchronization reads only documented Moonraker/Klipper server, printer, `configfile.settings`, and `toolhead` fields. Keep connection values server-side, sanitize all external text and numbers, and preserve manual manufacturer, model, nozzle material, extruder type, and notes.
16. Canonical inventory changes queue Spoolman projection immediately. The one-minute safety sweep must first import printer-recorded usage, then converge every vendor, filament, and spool so an empty/rebuilt Spoolman database and missed/dead jobs repair automatically. Provision managed custom fields through the supported API, JSON-encode their values, preserve unknown fields, paginate complete collections, and never overwrite remote remaining weight during metadata-only convergence.
17. The persisted `FILAMENT_MANAGER_SPOOL_STATE` Klipper macro is the physical loaded-spool authority after one-time initialization. A completed physical unload must clear Moonraker/Spoolman before insertion, and a completed physical load must set the exact new Spoolman ID; a requested target is never active early. The worker repairs direct Moonraker/Fluidd active-spool drift back to the last completed physical boundary every 15 seconds in every initialized workflow phase before aligning canonical state.
18. Cura print preflight uses the managed material GUID and the bounded printer-side catalog to bypass a change only when the physical spool matches. Otherwise Fluidd must prompt for one exact eligible spool and confirmation of insertion. Keep `integrations/klipper/filament-manager-macros.cfg` as the complete reference, include it after the printer's existing motion macros, preserve those routines through wrappers, and leave Fluidd's independent print-start spool selector disabled.
19. The worker automatically aligns the configured printer's exact P-number build-plate side with Moonraker every 15 seconds and refreshes sanitized printer information every 5 minutes. Preserve these automatic defaults, keep manual integration actions optional, and never log connection credentials or external response bodies.

## Required stack

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL, and psycopg 3
- React, TypeScript, and Vite
- PostgreSQL-backed jobs using transactional outbox, `FOR UPDATE SKIP LOCKED`, and advisory locks
- Pytest, Ruff, mypy, Vitest, and Playwright
- Structured JSON logging, Prometheus metrics, multi-stage Docker builds, and separate Swarm stack files

Do not add Redis, Celery, Kafka, or another message broker without an approved architecture decision.

## Agent routing

- [Database and migrations](skills/database.md)
- [Security and local-role authentication](skills/security.md)
- [Frontend design and accessibility](skills/frontend.md)
- [Testing and validation](skills/testing.md)
- [Docker, Swarm, and operations](skills/deployment.md)

Read the relevant skill before changing that area. The numbered source specifications are under `docs/specification/`.

## Visual contract

Use the approved Workshop Navy design system in [docs/design/palette.png](docs/design/palette.png), including its paired light and dark modes. The implementation references are under `docs/design/concepts/`. Keep spacing uniform and preserve the table-driven and workflow-driven layouts shown there.

## Core implementation rules

- UUID technical keys, immutable human spool IDs, integer record versions, UTC storage, and America/Detroit display.
- PostgreSQL `NUMERIC`, never binary floating point, for mass, density, dimensions, calibrated factors, and money.
- Immutable measurement, usage, audit, and calibration-result history.
- Optimistic concurrency for mutable resources and idempotency keys for external writes and device events.
- Every canonical mutation records an audit event and creates external projection jobs in the same transaction when required.
- Preserve unknown Spoolman `extra` fields.
- Treat spool locations as bounded free text. Import a Spoolman location only for a legacy canonical row that has never established location ownership; thereafter project the Filament Manager value back through the supported REST API.
- Google or Spoolman outages must queue work and must not corrupt canonical state.
- Workers coordinate immediate outbox delivery, one-minute complete Spoolman convergence, and Google publication with PostgreSQL advisory locks. Reclaim abandoned running jobs after the configured lock timeout.
- NFC UIDs are identifiers, not credentials. Scale readings remain telemetry until stability and identity checks pass.
- Workstation pairing codes are single-use and short-lived; agent bearer credentials are hashed, revocable, scoped only to agent endpoints, and never logged.
- Material templates are printer/nozzle scoped and revisioned. Every product profile revision directly links to one published template revision, stores only sparse differences, and retains a complete resolved snapshot for immutable publication and export. A newer template revision never moves linked filaments automatically: show the proposed effective changes and require a separate confirmation for each filament before creating its rebased draft.
- Material comparison is read-only and uses a profile baseline against another profile or any saved template revision. Show only semantically different canonical/additional Cura settings, normalize equivalent decimal representations, and allow cross-printer/nozzle comparisons only with a clear scope warning.
- Cura deployments must wait for Cura to close, match exactly one machine/nozzle, back up every affected user material and managed plugin file, use atomic replacement, and preserve all machine, quality, and start-G-code configuration. Authoritative takeover must remain opt-in when unmanaged user materials exist.
- The workstation agent never patches Cura machine start G-code. Operators configure the documented `FILAMENT_MANAGER_START_PRINT ... MATERIAL_GUID={material_guid}` call once and preserve every unrelated Cura start/end command.
- Treat active-spool identity as observed physical state, not a selectable metadata field. Inventory actions and public load/activate macros request the guarded unload/insert/load workflow; only the post-motion commit helper may call Moonraker's active-spool method directly.
- Preserve initial physical build-plate identifiers `P1` through `P5` exactly. An unsuffixed mesh such as `P4` is Side A; `P4b` is Side B of the same physical P4 plate. Additional plates are discovered from exact `P<number>` or `P<number>b` Moonraker bed-mesh profiles; never accept arbitrary mesh names as G-code input.
- Published material profiles and material-template revisions are immutable; changes create new versions.
- The ordered calibration workflow has seven steps. Size and Hole Calibration is required after Retraction and stores raw design/measured values plus server-calculated Cura `xy_offset` and `hole_xy_offset`; profile publication inherits the complete starting snapshot before applying results.

## Documentation and release discipline

Keep `README.md`, `CHANGELOG.md`, `USER_CHANGELOG.md`, `VERSION`, this file, and affected skill files synchronized with meaningful changes. Changelog versions use `MM.DD.YYYY` dates and always contain Added, Changed, and Fixed sections.

Do not commit, push, tag, publish images, or create a release unless the user explicitly authorizes that boundary.
