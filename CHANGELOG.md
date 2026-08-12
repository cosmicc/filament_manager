# Changelog

## Unreleased - 08.11.2026

### Added

- Added physical build plates with independent Side A and Side B records. `P4` represents Side A and `P4b` represents Side B of the same physical P4 plate.
- Added a plate description plus per-side surface material, smooth/textured finish, notes, mesh availability, mesh check time, and mesh calibration time.
- Added Administrator-triggered Moonraker synchronization that automatically creates bounded exact `P<number>` and `P<number>b` plate sides and records an audit event.
- Added the operator's current Cura Material Settings catalog, sanitized discovery of existing Cura materials, and explicit import into new draft profiles.
- Added material-only Cura rendering for all approved settings, including Cura Klipper Settings pressure advance and smooth time.
- Added versioned generic material templates scoped to a printer and nozzle, publication, and template provenance for copied product profiles.
- Added web workflows for creating templates and revisions, adding filament products from published templates, and adding physical spools without opening Spoolman.
- Added automatic Alembic upgrades before web and worker startup with a bounded PostgreSQL advisory lock and fail-closed error handling.
- Added authoritative full-library Cura synchronization, checksum-based drift repair, transactional cleanup/rollback of user material files, and a managed visibility plugin that hides bundled Cura materials.
- Added one-time adoption of existing Spoolman free-text spool locations and an in-app bucket/location editor.

### Changed

- Kept P1-P5 as the initial physical set while allowing later plates and optional B sides to come from same-named saved Moonraker meshes.
- Changed selection, calibration context, dashboard state, and material preferences to record the exact plate side facing up.
- Changed Cura deployment to write one material file rather than quality-change profiles or machine start-G-code patches. The Material Settings and Klipper Settings plugins now consume the material values.
- Changed synchronization to align the selected printer's active physical plate and side with Moonraker while preserving existing physical and side metadata.
- Documented the hash-bound dry-run and commit procedure for importing the initial workbook with one-shot Swarm jobs.
- Changed new filament products to copy a published generic template into an independently tunable draft material profile.
- Changed Cura deployment from one selected profile to the latest published templates and product profiles as one desired-state library. Existing workstations with user materials require explicit Administrator takeover.
- Changed Compose and Swarm upgrades to migrate automatically; a one-shot migration remains only for diagnosis and recovery.
- Changed spool-location ownership so Filament Manager becomes authoritative after import, edit, or explicit clearing and repairs later Spoolman-side drift.

### Fixed

- Fixed the initial `SELECT_BUILD_PLATE` macro state using an unambiguous Python literal so Klipper accepts the macro during startup.
- Fixed double-sided plates and different per-side meshes being impossible to represent.
- Fixed later physical plates being impossible to represent because the database column, JSON contracts, API client, macro, and interface were limited to P1-P5.
- Fixed lexicographic plate ordering that would place P10 before P2.
- Prevented missing Moonraker meshes from deleting or overwriting canonical physical-plate and side details; they are retained and shown as unavailable.
- Fixed web and worker replicas racing database upgrades or requiring the operator to pre-run every schema update.
- Fixed clean Cura installations requiring manual first synchronization and managed Cura material files drifting away from canonical Filament Manager state.
- Fixed routine product, spool, and generic-material setup requiring direct API or Spoolman access.
- Fixed the shipped build-plate macro default to use the explicit quoted `"UNSET"` string and documented how to locate stale included copies.

## 0.1.4 - 08.11.2026

### Added

- Added an Administrator-only Printers page action that seeds the configured Moonraker printer and P1-P5 build plates from deployment environment variables.
- Added a shared idempotent first-run seed service for configured printers and P1-P5 build plates.

### Changed

- Changed browser workbook commit to auto-seed missing configured system records in the same transaction before importing printer-scoped material profiles.
- Changed the CLI `seed-system` command to use the same seed service as the web import flow.

### Fixed

- Fixed the Printers page empty state incorrectly telling Docker operators to edit a server-side YAML file.
- Fixed first-run browser workbook commits failing with `seed the configured printer before importing profiles` when the operator had not run the separate seed CLI command.

## 0.1.3 - 08.11.2026

### Added

- Added Administrator-only `.xlsx` workbook upload endpoints for dry-run validation, recent import run inspection, and explicit commit.
- Added a Settings workbook import panel that uploads the master workbook, shows validation totals and row findings, and commits a validated uploaded run.
- Added integration coverage for browser workbook upload, commit, audit recording, and projection outbox creation.

### Changed

- Changed workbook import reporting so uploaded runs retain the user-visible source filename while still committing only hash-verified stored bytes.
- Queued a Google inventory publication job after workbook import commits so the read-only publication target can rebuild from canonical state.
- Updated installation guidance to use the web import flow first and keep CLI import commands as a recovery path.

### Fixed

- Fixed the shared frontend request helper so multipart workbook uploads are not sent with a JSON content type.

## 0.1.2 - 08.11.2026

### Added

- Added regression tests for the trusted-host-aware web readiness probe and the non-HTTP worker health-check contract.

### Changed

- Changed the image readiness probe to connect over loopback while presenting the exact hostname from `FILAMENT_MANAGER_BASE_URL`.
- Disabled the inherited HTTP health check for worker and local one-shot services that do not listen on the web port.
- Updated one-shot Swarm migration, seed, and Administrator bootstrap commands to disable the image health check explicitly.

### Fixed

- Fixed Filament Manager web tasks being rejected as unhealthy when trusted-host middleware returned `400 Bad Request` to the old loopback-host probe.
- Fixed healthy worker tasks being replaced because they inherited a readiness probe for an HTTP server they do not run.

## 0.1.1 - 08.11.2026

### Added

- Added a root `docker-stack.yml` that deploys Filament Manager, its worker, and Spoolman together against remote PostgreSQL.
- Added a complete environment-only stack-variable contract for application URLs, one Moonraker printer, Google publication, operational tuning, credentials, and remote PostgreSQL.
- Added complete remote PostgreSQL provisioning, migration, stack deployment, seed, and first-user instructions.
- Added automated post-CI AMD64 and ARM64 GHCR publication with testing-oriented `latest` and immutable commit tags.

### Changed

- Made the combined remote-database stack the default production installation while retaining the independent stack files for operators who need separate application lifecycles.
- Expanded stack variables for remote database routing, scoped credentials, published endpoints, integration origins, one-printer settings, and operational tuning.
- Made independent-stack network and persistent-volume object names deployer-selectable variables.
- Changed Docker Compose and Swarm deployments to use ordinary environment variables instead of Docker secrets for the current testing phase.
- Added masked inline credential support for the canonical database, Moonraker, Google publication, and the one-shot Administrator bootstrap.
- Documented how existing deployments can preserve current credential values during the variable migration and remove obsolete Docker secret objects only after verification.
- Removed the external Docker-config prerequisite; Docker services now build their complete validated configuration directly from environment variables.
- Limited the current Docker deployment contract to one Moonraker printer and made it derive the WebSocket URL from the HTTP URL when no override is supplied.
- Changed the canonical database role to `filament_user` and made both PostgreSQL clients explicitly disable TLS for the isolated database network.

### Fixed

- Corrected the Swarm instructions to explicitly export `.env` values because `docker stack deploy` does not load `.env` automatically.
- Used Spoolman's supported async PostgreSQL query syntax for explicit non-SSL connections and removed an unsupported allowed-host variable that could imply protection the pinned image does not provide.
- Removed obsolete Docker secret mounts and the local secret-copy entrypoint so every current Docker deployment path follows the stack-variable contract.
- Removed baked example hostnames and printer details from the active Docker configuration path.
- Corrected workstation pairing configuration construction and included the audit tool in agent development dependencies so strict CI runs through completion.

## 0.1.0 - 08.05.2026

### Added

- Complete FastAPI, React, and PostgreSQL Filament Manager application with local Administrator, Operator, and Viewer accounts.
- Canonical inventory, immutable physical measurements and usage, material profiles, the exact six-step calibration workflow, printers, and P1-P5 build plates.
- Hash-bound workbook dry-run and commit import, QR spool labels, append-only audit history, transactional outbox, and scheduled reconciliation workers.
- Supported Spoolman REST, Moonraker, Google Sheets publication, local Docker Compose, independent production Swarm stacks, migrations, health checks, metrics, and operational documentation.
- Workshop Navy light and dark design system, responsive printer-side weighing flow, automated backend/frontend tests, and rendered validation references.
- Cross-platform Cura workstation agent for Arch Linux and Windows 11 with one-time pairing, automatic Cura/machine discovery, outbound-only deployment polling, complete material and quality profile rendering, guarded pressure-advance injection, automatic backup, atomic writes, checksums, and rollback.
- Cura workstation management and deployment history UI, one-click deployment to every active agent, hardened systemd user and Windows logon-task installers, standalone binary build workflow, API lifecycle tests, and isolated local-agent tests.

### Changed

- Standardized the product and all technical identifiers on Filament Manager.
- Made PostgreSQL authoritative while preserving standalone Spoolman as the printer-facing operational service and the workbook as an initial-import fixture.
- Adapted the approved Workshop Navy palette into consistent light and dark application themes.
- Replaced the frontend routing dependency with a small same-origin History API router after dependency review.
- Changed Cura profile delivery from download-only JSON to optional automated, agent-scoped deployment while retaining manual export.

### Fixed

- Preserved the corrected `P11-S` workbook identifier so every imported physical spool code is unique.
- Made the initial migration fully reversible, preserved unknown Spoolman extension fields, and established an unknown tare atomically with its first measurement.
- Raised the development test-tool floor to the patched Pytest 9 release identified by dependency audit.
- Removed package-manager and build tooling from the non-root production image after runtime dependency audit.
- Separated local PostgreSQL administrator, canonical application, and Spoolman roles and limited the bootstrap password to its one-shot Compose service.
- Preserved restrictive host secret permissions during local PostgreSQL initialization through an ephemeral privilege-drop handoff.
- Prevented Cura writes while Cura is running, path escapes and symlink traversal, ambiguous machine targeting, unbounded agent metadata, credential replay, and unsafe replacement of unknown inherited start G-code.
