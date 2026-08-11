# Changelog

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
