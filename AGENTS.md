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
7. Cura files are changed only by the outbound-only per-user workstation agent under `workstation-agent/`; the server never reaches into a workstation or listens on an agent port. After explicit takeover of a workstation with existing user materials, Filament Manager owns the complete user material library, synchronizes the current templates under the exact `Template <material type>` name and `Template` brand plus every current product profile, removes stale user material files after backup, and installs its visibility plugin so bundled Cura materials are hidden. The Cura Material Settings plugin exposes stored values, and the Cura Klipper Settings plugin owns pressure advance and smooth time; never patch machine start G-code or create quality-change profiles.
   Re-running either supported workstation installer is an in-place upgrade: identify fresh installation versus upgrade in its output, preserve pairing credentials and Cura backup/state data, replace only managed code and service/task definitions, and restart only an agent that was already running. The supported uninstallers remove the per-user service/task and all agent-owned executable, credential, state, and backup files without deleting the currently deployed Cura material/plugin library.
   Before authoritative takeover, an Administrator maps any subset of reported Cura materials or saved print profiles to existing active templates, with one source and one template used at most once in the batch. Read saved print profiles without modifying Cura, merge their global and first-extruder layers, import only approved literal settings, and never evaluate Cura expressions. A single confirmation applies every mapping atomically, records provenance, updates linked profiles through normal inheritance, enables authoritative management, and queues synchronization; unmapped sources are intentionally discarded after backup.
   After takeover, the agent may report bounded approved setting changes only for known deterministic managed material GUIDs. Each semantic change saves directly and idempotently to the matching current template or profile, cascades template inheritance immediately, and queues synchronization. Never admit a new Cura-created material into canonical state.
8. Docker deployments are environment-only: every deployer-supplied application setting and credential comes from scoped stack variables, with no mounted application Docker config and no Docker secrets. The current variable contract supports exactly one Moonraker printer. Treat credential variables as a transitional risk, restrict manager and Portainer access, keep populated `.env` files untracked with mode `0600`, and never log or render these values.
9. The container image health check is web-specific: it probes loopback with the public hostname from `FILAMENT_MANAGER_BASE_URL` so trusted-host validation remains enforced. Every worker or one-shot service must disable this inherited HTTP health check.
10. Successful CI for a `main` push publishes the Filament Manager container for AMD64 and ARM64 with `latest` and immutable `sha-<commit>` tags. Treat `latest` as a testing convenience; production deployments pin an immutable SHA tag or digest. Image publication does not authorize a Git tag or GitHub Release.
11. Remote PostgreSQL connections use `filament_user` and `spoolman_user` with TLS explicitly disabled on the operator-managed isolated database network. Preserve SCRAM authentication, narrow firewall and `pg_hba.conf` rules, and separate database ownership; this non-SSL contract is unsafe on shared or untrusted networks.
12. The container entry point automatically upgrades the Filament Manager schema before starting web or worker commands. Concurrent tasks coordinate with one bounded PostgreSQL session advisory lock; a failed or timed-out migration must stop startup. Keep the opt-out only for controlled recovery.
13. Filament Manager owns spool locations after initial adoption. A legacy spool with no canonical location may import one existing bounded free-text Spoolman location; every local edit, including clearing the field, makes the canonical value authoritative and reconciliation repairs later remote drift.
14. `filament_colors` owns the case-insensitive mapping from a human color name to its six-digit screen sample. A sample change updates every matching product mirror and queues their Spoolman projections; never treat per-product color hex as independent state.
15. Printer information synchronization reads only documented Moonraker/Klipper server, printer, `configfile.settings`, and `toolhead` fields. Keep connection values server-side, sanitize all external text and numbers, and preserve manual manufacturer, model, nozzle material, extruder type, and notes.
16. Canonical inventory changes queue Spoolman projection immediately. The one-minute safety sweep must first import printer-recorded usage, then converge every vendor, filament, and spool so an empty/rebuilt Spoolman database and missed/dead jobs repair automatically. Provision managed custom fields through the supported API, JSON-encode their values, preserve unknown fields, paginate complete collections, and never overwrite remote remaining weight during metadata-only convergence.
17. The persisted `FILAMENT_MANAGER_SPOOL_STATE` Klipper macro is the physical loaded-spool authority after one-time initialization. A completed physical unload must clear Moonraker/Spoolman before insertion, and a completed physical load must set the exact new Spoolman ID; a requested target is never active early. A direct non-null Spoolman selection made while idle or waiting for a manual target becomes a guarded Fluidd confirmation/load target, then the worker restores Spoolman to the last completed physical boundary until confirmation. Direct clears, invalid selections, and drift during other phases are repaired without changing canonical state.
18. Cura print preflight uses the managed material GUID and the strict published-profile printer-side catalog to bypass a change only when the physical spool matches. Otherwise Fluidd must prompt for one exact eligible print spool and confirmation of insertion. Manual `LOAD_FILAMENT`, `FILAMENT_MANAGER_LOAD_TARGET`, M600 selection, and guarded direct Spoolman targets use a separate live catalog of projected non-empty spools with a safe temperature from the newest non-archived exact profile or linked in-scope template; manual loading must not require publication or a separately staged macro variable. Keep `integrations/klipper/filament-manager-macros.cfg` as the complete reference, include it after the printer's existing motion macros, preserve those routines through wrappers, and leave Fluidd's independent print-start spool selector disabled.
19. G-code inspection defaults to warning while retaining evidence. Administrators may enable blocking; then an unresolved exact profile, unavailable bounded inspection, or supported mismatch must pause in Fluidd before spool selection. Read files only through supported Moonraker metadata/download endpoints, hash the complete bounded stream, retain bounded samples, and never evaluate Cura content.
20. Canonical print history imports supported Moonraker history and captures new exact state only after preflight finishes. Preserve immutable printer/spool/product/profile/plate snapshots, G-code hashes, explicitly unresolved legacy state, and append-only M600 material segments and outcome-assessment revisions. Never relink historical records to current mutable state.
21. Operator notifications are persistent, deduplicated canonical events with per-user read state. Reappearing resolved conditions become unread. Keep unavailable Moonraker, dead job, low/empty spool, plate maintenance, and failed Cura synchronization checks server-side and never expose external response bodies.
22. New/reset local accounts use temporary passwords and must change them before accessing other application routes. Revoke sessions on deactivation/reset, retain last-Administrator and self-deactivation safeguards, and never return or retain plaintext passwords.
23. The worker automatically aligns the configured printer's exact P-number build-plate side with Moonraker every 15 seconds and refreshes sanitized printer information every 5 minutes. Preserve these automatic defaults, keep manual integration actions optional, and never log connection credentials or external response bodies.
24. Physical nozzles are canonical inventory records with diameter, construction material, lifecycle status, and append-only install/remove events. A printer may have at most one installed nozzle. Exact completed-print attribution and total filament use follow the nozzle captured on the immutable print job; do not rewrite history when a nozzle is later moved or retired.
25. Diagnostics is the single web surface for connection, synchronization, worker, queue, bounded operational error, and running/latest-version status. Its authenticated text download is generated from the same sanitized bounded overview. Query only the fixed public GitHub releases endpoint, include non-draft testing releases, cache results, and never expose upstream response bodies. Recovery validation is read-only and results are persisted; projection rebuilds only queue reconstructable Spoolman, Google, and managed Cura work and never mutate canonical business records or perform a live database restore. Never render or export credentials, URLs, SQL, external response bodies, or tracebacks.

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

Keep the running version visible in the application shell. Keep light/dark selection in Settings, use a single icon-labelled Logout action without an account pill, and use only directional chevrons for the desktop sidebar collapse/restore control.

## Core implementation rules

- UUID technical keys, immutable human spool IDs, integer record versions, UTC storage, and America/Detroit display.
- PostgreSQL `NUMERIC`, never binary floating point, for mass, density, dimensions, calibrated factors, and money.
- Immutable measurement, usage, audit, and calibration-result history.
- Optimistic concurrency for mutable resources and idempotency keys for external writes and device events.
- Every canonical mutation records an audit event and creates external projection jobs in the same transaction when required.
- Preserve unknown Spoolman `extra` fields.
- Quantize Spoolman remaining-weight readings to the canonical `NUMERIC(12,3)` gram precision before comparing, recording usage, or building idempotency keys.
- Treat spool locations as bounded free text. Import a Spoolman location only for a legacy canonical row that has never established location ownership; thereafter project the Filament Manager value back through the supported REST API.
- Google or Spoolman outages must queue work and must not corrupt canonical state.
- Workers coordinate immediate outbox delivery, one-minute complete Spoolman convergence, and Google publication with PostgreSQL advisory locks. Reclaim abandoned running jobs after the configured lock timeout.
- NFC UIDs are identifiers, not credentials. Scale readings remain telemetry until stability and identity checks pass.
- Workstation pairing codes are single-use and short-lived; agent bearer credentials are hashed, revocable, scoped only to agent endpoints, and never logged.
- Material templates are printer/nozzle scoped. User-facing edits save directly, while the database appends hidden immutable current-state snapshots for audit, exact print history, synchronization, and recovery. Every product profile links to the current template snapshot, stores only sparse explicit differences, and retains a complete resolved snapshot. Saving a template immediately creates current snapshots for every linked filament; preserve each profile's explicit override keys even when an override temporarily equals the new template value.
- Pre-takeover Cura source provenance is unique per workstation and source, and each template may be targeted once in the atomic takeover batch. Sources may be hardened material XML or read-only saved print-profile settings. Only approved mappings directly update existing templates; unmapped sources are ignored and no source creates a new template or product.
- Material comparison is read-only and uses a current profile baseline against another current profile or current template. Show only semantically different canonical/additional Cura settings, normalize equivalent decimal representations, and allow cross-printer/nozzle comparisons only with a clear scope warning.
- Managed Cura synchronization must wait for Cura to close, match exactly one machine/nozzle, back up every affected user material and managed plugin file, use atomic replacement, and preserve all machine, quality, and start-G-code configuration. Authoritative takeover must remain opt-in when unmanaged user materials exist.
- The workstation agent never patches Cura machine start G-code. Operators configure the documented `FILAMENT_MANAGER_START_PRINT ... MATERIAL_GUID={material_guid}` call once and preserve every unrelated Cura start/end command.
- Treat active-spool identity as observed physical state, not a selectable metadata field. Inventory actions and public load/activate macros request the guarded unload/insert/load workflow; a direct Spoolman selection may supply a pending target but requires Fluidd confirmation and is restored to the physical ID until completion. Only the post-motion commit helper or explicit already-loaded confirmation may establish a new physical ID.
- Preserve initial physical build-plate identifiers `P1` through `P5` exactly. An unsuffixed mesh such as `P4` is Side A; `P4b` is Side B of the same physical P4 plate. Operators may add the one canonical Side B record manually; it remains unavailable until the exact same-named Moonraker mesh is discovered. Additional plates are discovered from exact `P<number>` or `P<number>b` profiles; `SELECT_BUILD_PLATE` without parameters generates its prompt from that live saved-mesh dictionary, and arbitrary mesh names must never become G-code input.
- A completed print increments each distinct captured spool once, even if a spool appears in multiple material segments, and increments its captured physical nozzle and build-plate side once. Derive totals from immutable completed print history rather than mutable counters.
- Material profile and template snapshots are immutable internal history. User-facing create/edit/calibration operations save directly as the new current state and automatically queue projections; never expose draft, publish, revision, or manual Cura deployment steps.
- The ordered calibration workflow has seven steps. Size and Hole Calibration is required after Retraction and stores X/Y/Z, hole, shaft, and wall design/measured values plus server-calculated Cura expansion and flow, material shrinkage, and non-applying printer-geometry recommendations; applying calibration results inherits the complete starting snapshot before saving material changes.
- Build-plate cleaning and per-side mesh events are append-only. Due state uses the plate's configurable print-count and day thresholds; clearing an active side must clear Moonraker's mesh before reconciliation clears canonical context.

## Documentation and release discipline

Keep `README.md`, `CHANGELOG.md`, `USER_CHANGELOG.md`, `VERSION`, this file, and affected skill files synchronized with meaningful changes. Changelog versions use `MM.DD.YYYY` dates and always contain Added, Changed, and Fixed sections.

Do not commit, push, tag, publish images, or create a release unless the user explicitly authorizes that boundary.
