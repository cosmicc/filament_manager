# Changelog

## 0.2.3 - 08.18.2026

### Added

- Added an idempotent `Template ASA` starting profile for each configured printer/nozzle scope so an existing Cura ASA profile has a canonical takeover target.
- Added an explicit two-stage Cura takeover dialog where Administrators map each reported material or saved print profile to an existing template, then review the complete batch before confirmation.
- Added clear visual highlighting for every filament setting that is explicitly customized instead of inherited from its linked template.
- Added custom named filament colors, two- or three-color palettes, and rainbow spool swatches across inventory, dashboard, and labels.
- Added complete filament and spool correction editors plus safe delete-or-archive actions.
- Added automatic empty-spool tare calculation from the entered filament amount and optional full-spool scale weight.

### Changed

- Changed the filament settings editor to render the complete effective template-linked values while continuing to persist only semantic differences as sparse filament overrides.
- Changed filament settings into Cura-like temperature, flow, speed, retraction, cooling, support, dimensional, filament, Klipper, and build-plate groups with no catch-all advanced section.
- Changed customized-setting highlighting to update immediately while editing and remain visible after saving.
- Changed user-facing numeric values to compact field-specific precision with no displays beyond two decimal places.
- Changed completed, failed, and cancelled jobs to deduct only actual Moonraker-reported segment use from each exact spool, without a predicted fallback or duplicate deductions.
- Changed filament colors to remain editable until the filament has retained spool-use or print history, after which identity is locked for historical consistency.
- Changed overlapping Cura retract-speed and maximum-fan aliases to use one canonical application control while still writing the required deterministic alias values to Cura.
- Changed workstation discovery to keep named Cura materials and saved print profiles selectable even when they contain no tracked literal overrides or only safely omitted expressions.
- Changed all server, frontend, and workstation-agent version surfaces to 0.2.3.

### Fixed

- Fixed periodic workstation heartbeats invalidating an open Cura mapping review with `Workstation changed; reload and retry`; takeover now locks against the exact reviewed Cura source catalog instead of unrelated workstation activity.
- Fixed the workstation agent using HTTPX's bundled public CA file instead of the operating-system trust store, which prevented heartbeats and Cura profile discovery on installations secured by a locally trusted private CA.
- Fixed duplicate retraction-speed and maximum-fan controls appearing under both grouped profile settings and Additional Cura Material Settings.
- Fixed Cura takeover showing zero importable profiles when discovered saved profiles contained only inherited Cura expressions or no literal settings tracked by Filament Manager.
- Fixed **Back to mappings** returning to a workstation card without an unmistakable source-to-template mapping screen.
- Fixed the Arch workstation service failing Cura deployment when its platformdirs title-case state root did not exist beneath systemd read-only home protection.
- Fixed new-spool gross weight being rejected instead of deriving empty-spool tare from gross weight minus filament amount.
- Fixed setup mistakes lacking a safe delete path and incomplete spool/filament editors preventing correction of original setup fields.
- Fixed terminal failed and cancelled jobs not reducing exact spool inventory from their reported actual filament use.

## 0.2.2 - 08.17.2026

### Added

- Added physical nozzle inventory with diameter, construction material, lifecycle status, printer installation history, completed-print count, and total filament use.
- Added completed-print counts to each spool and build-plate side. A completed print counts once for every distinct spool used, including distinct M600 material segments.
- Added manual Side B creation for an existing physical P-number plate; the new `P<number>b` side remains unavailable until Moonraker discovers its exact same-named mesh.
- Added a dedicated Diagnostics page for connection, synchronization, worker, queue, and operational status; bounded recent errors; persisted recovery-validation results; safe projection rebuilds; and job retry/reconciliation controls.
- Added the running Filament Manager version to the application shell and Diagnostics, plus a cached Diagnostics comparison with the newest non-draft GitHub release, including testing prereleases.
- Added `filament-manager-cli verify` for read-only recovery validation and `filament-manager-cli rebuild-projections --confirm` for safe full projection requeueing.
- Added an atomic one-time Cura takeover that lists every discovered source with an existing-template selector, allows any source to remain unmapped, reviews all choices together, and records source/template provenance.
- Added read-only discovery of saved Cura print profiles during one-time takeover, including merged global/first-extruder settings, machine and quality metadata, tracked literal settings, and safely omitted expression counts.
- Added Arch Linux and Windows workstation-agent uninstallers that remove the per-user service/task, executable, pairing credential, local state, and agent backups while leaving Cura's current managed library in place.
- Added an authenticated **Download log** action on Diagnostics that exports the current bounded, sanitized operational report as a plain-text file.

### Changed

- Moved live connection, synchronization, worker, queue, and error information from Dashboard, Printers, Integrations, and Cura Workstations into Diagnostics.
- Changed template, filament-profile, calibration, workbook-import, and managed Cura edits to save directly as current settings, automatically queue projections, and keep versioned snapshots only as hidden immutable history.
- Changed template saves to update every linked filament profile immediately while preserving each explicit customized setting, even when its value temporarily matches the new template.
- Changed Cura takeover to map each selected source directly to an existing template, allow each source/template once, ignore unmapped sources, and apply all template changes plus linked-profile inheritance in one confirmed transaction.
- Changed print-profile import to accept only settings tracked by Filament Manager and omit unevaluated Cura expressions.
- Changed printer nozzle editing to use installed physical nozzle records; installation and removal are recorded as append-only lifecycle events.
- Changed all server, frontend, and workstation-agent version surfaces to 0.2.2.
- Changed `LOAD_FILAMENT`, `FILAMENT_MANAGER_LOAD_TARGET`, and M600 replacement selection to use a dedicated live manual-load catalog without a hidden macro-variable prerequisite. Non-empty projected spools may use their newest exact profile or linked template temperature, while Cura print preflight still requires a current exact profile.
- Changed direct non-null Spoolman selections into guarded Fluidd target confirmations: the worker restores the last physical ID until the operator confirms an existing load or completes the unload/load routine.
- Changed the application shell to show only an icon-labelled Logout action and directional sidebar chevrons, and moved the persistent light/dark theme control to Settings.
- Changed `SELECT_BUILD_PLATE` without parameters to build its chooser live from Klipper's saved exact P-number meshes.
- Changed workstation installers to state clearly whether they are performing a fresh installation or an upgrade while retaining conditional restart and rollback behavior.
- Changed stale Cura-agent diagnostics to identify the last contact and recommend checking or upgrading the workstation service.
- Changed aggregate Moonraker reconciliation errors to retain bounded exception-class counts without exposing tracebacks, external responses, URLs, or database details.

### Fixed

- Fixed the missing workflow for adding the second printable side of an existing physical build plate.
- Fixed operational status being fragmented across unrelated pages instead of providing one reviewable diagnostics surface.
- Fixed pre-takeover Cura preservation lacking a clear per-source destination selector and one atomic completion step.
- Fixed saved Cura print settings being absent from the one-time takeover import and therefore unavailable for preservation before authoritative synchronization.
- Fixed user-facing material workflows requiring draft creation, publication, per-filament template-update confirmation, or manual Cura deployment instead of direct saves and automatic synchronization.
- Fixed manual filament loading dead-ending with “Select a Target Spool” even after `FILAMENT_MANAGER_LOAD_TARGET` was run.
- Fixed valid non-empty Spoolman spools being hidden from manual loading solely because they lacked a current exact printer/nozzle print profile.
- Fixed rerunning M600 during an unfinished selection reporting only that a workflow was active instead of reopening the exact-spool chooser.
- Fixed direct Spoolman selections disappearing without a safe way to use them as the requested physical target.
- Fixed the build-plate selector requiring static per-mesh macros whenever another valid mesh was saved.
- Fixed Klipper startup failing when a configuration transfer or editor collapsed an empty catalog-revision macro literal.
- Fixed Diagnostics comparing the canonical PostgreSQL schema with the superseded pre-0.2.2 Alembic revision.
- Fixed fractional Spoolman remaining-weight values repeatedly creating the same usage event and dead reconciliation job after PostgreSQL rounded the stored mass.
- Fixed a failed live-print capture expiring its SQLAlchemy printer object and causing `MissingGreenlet` during subsequent Moonraker history reconciliation.

## 0.2.1 - 08.13.2026

### Added

- Added canonical print history synchronized from Moonraker, including exact printer, spool, material-profile revision, build-plate side, G-code hash, slicer metadata, predicted/actual use, immutable M600 material segments, and explicitly unresolved legacy records.
- Added bounded G-code inspection of Moonraker metadata and Cura headers, with profile mismatch evidence and an Administrator setting that changes the default warn-and-continue behavior to fail-closed blocking in Fluidd.
- Added append-only print assessments with Excellent, Successful, Acceptable, and Failed ratings, optional defect tags, notes, and profile-version success statistics.
- Added full dimensional calibration for X, Y, Z, holes, shafts, and wall thickness, including Cura expansion/flow results, material shrinkage, and non-applying printer-geometry recommendations.
- Added two-to-four-column profile/template revision comparison with difference-only rows, cross-scope warnings, success rates, low-sample labels, and template N/A states.
- Added account editing, activation controls, temporary-password reset, forced password replacement, build-plate maintenance ledgers/reminders, explicit active spool/plate clearing, responsive mobile data cards, and a persistent per-user notification center.

### Changed

- Changed new local accounts to require replacement of their Administrator-supplied temporary password before any other application route is available.
- Changed Moonraker print-state polling to every five seconds by default and added complete supported-history import plus incremental reconciliation.
- Changed the supplied Klipper macro reference to gate optional blocking inspection before exact-spool selection while preserving the existing `START_PRINT`, `END_PRINT`, motion, cancellation, and purge implementations.
- Changed build plates to use configurable cleaning and mesh-calibration thresholds based on both elapsed days and completed-print counts.
- Changed all server, frontend, and workstation-agent version surfaces to 0.2.1.

### Fixed

- Fixed a preflight-paused print being able to record the previously loaded spool as its starting material before the requested spool was physically loaded.
- Fixed a completed live print being duplicated when Moonraker repeated its terminal state or the same job later appeared in history.
- Fixed M600 print-history segments lacking their own derived length and weight totals.
- Fixed a reactivated operator notification remaining read after the underlying condition recurred.

## 0.2.0 - 08.13.2026

### Added

- Added a Cura Workstations preservation workflow that imports selected reported Cura materials as source-tracked draft templates for review and publication before takeover.
- Added duplicate-safe Cura template-import provenance plus a server-side guard that blocks authoritative management until every selected import is active and published; distinct imported source variants can coexist with a base template of the same material type.
- Added repeated-install regression coverage for the Arch Linux and Windows workstation installers.
- Added a difference-only material comparator for profile-to-profile and profile-to-template-revision review, including complete canonical and additional Cura settings.
- Added Cura material-GUID print preflight with exact matching-spool choices in Fluidd, profile-specific unload/load temperatures, persistent physical-spool state, bounded printer catalog synchronization, and a complete Klipper/Moonraker macro reference.
- Added guarded manual load, unload, `M600`, active-spool, cancellation, purge-more, and resume paths that reuse the printer's existing physical routines.
- Added direct template-revision links, sparse per-filament overrides, complete resolved snapshots, inherited/customized field indicators, and per-filament template-update review.
- Added draft-only intake of setting changes made to known managed Cura templates and product materials; unchanged content is ignored, unknown or new Cura materials are rejected, and publication remains an explicit application action.

### Changed

- Changed both workstation installers to perform safe in-place upgrades when run again, preserving pairing configuration, Cura backups, and agent state while refreshing managed code and service/task definitions.
- Changed installer upgrades to restart the agent only when it was already running and to restore the previous standalone executable if replacement fails.
- Changed material comparisons to allow any printer/nozzle pairing while clearly warning when either scope dimension differs.
- Changed Inventory **Set active** to **Load spool**. The request now opens the confirmed printer workflow without changing canonical or Spoolman active state early.
- Changed 15-second Moonraker reconciliation to repair direct active-ID drift to the last completed physical Klipper state before synchronizing the application.
- Changed the server, frontend, and workstation-agent package versions to 0.2.0.
- Changed every template's application and Cura identity to `Template <material type>` under the `Template` brand, while continuing to synchronize one material entry for every published filament profile.
- Changed a published template update to require separate confirmation for each linked filament; confirmation creates a reviewable draft and preserves that filament's explicit overrides.

### Fixed

- Fixed overlong automatic Moonraker audit correlation IDs causing PostgreSQL `StringDataRightTruncation` errors in the worker.
- Fixed worker error reporting attempting to reuse an aborted database transaction, which obscured the original Moonraker synchronization failure with `PendingRollbackError`.
- Fixed repeated workstation-agent installation being unsafe while the existing agent executable or service task was running.
- Fixed aborted spool changes being able to leave a future target recorded as active: unload now clears only after motion completes, and load sets the new ID only after motion completes.
- Fixed the high-severity transitive `nanoid` development dependency advisory by updating the locked package to 3.3.18.
- Fixed profile/template ownership being implicit: profile details and history now identify the exact linked template revision and which settings are inherited or customized.

## 0.1.6 - 08.12.2026

### Added

- Added PostgreSQL-coordinated Moonraker polling for active spool and build-plate state every 15 seconds and sanitized printer information every 5 minutes.
- Added structured web, worker, scheduler, outbox, API rejection, validation, and Moonraker synchronization logs with error details and tracebacks where safe.
- Added browser-console diagnostics for every API request, including method, path, status, correlation ID, and safe rejection or network-error details.
- Added a shared accessible grouped-editor dialog and applied it to build plates, plate sides, printers, filaments, material profiles, templates, Cura imports, spools, users, and calibration setup.
- Added active-printer state to spool API responses and visible active indicators in inventory.

### Changed

- Changed the configured printer's active spool to follow Moonraker's supported Spoolman selection automatically, including selection changes and clearing.
- Changed in-app active-spool selection to update canonical state immediately in the same transaction that queues the Moonraker request.
- Changed Build Plates and Printers to display automatic synchronization freshness instead of requiring manual synchronization buttons.
- Changed Build Plates and Printers to use full-width summaries, grouped facts, side-by-side surface/status sections, and consistent edit actions instead of narrow cards and fold-down forms.
- Changed material setting editors to keep every supported Cura field visible in named groups instead of hiding additional settings in a fold-down section.
- Changed the dashboard, spool inventory, build plates, and printers to refresh operational state every 15 seconds.
- Changed the server and workstation-agent package versions to 0.1.6.

### Fixed

- Fixed printer and build-plate information remaining stale until a broken manual synchronization request was attempted.
- Fixed spool selections made through Klipper, Moonraker, or Spoolman not being reflected as active in Filament Manager.
- Fixed failed background scheduling or job claiming being able to stop ongoing synchronization without a diagnostic traceback.
- Fixed editing controls being inconsistently embedded, hidden, or expanded across different pages.

## 0.1.5 - 08.11.2026

### Added

- Added projection-aware Spoolman readiness checks, automatic managed custom-field provisioning, complete API pagination, and duplicate-safe managed UUID discovery.
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
- Added a case-insensitive remembered color library, real color swatches and pickers, and global propagation to every existing and future filament using the same color name.
- Added filament detail editing with every approved Cura Material Settings value, immutable profile revision history, and in-app draft creation and publication.
- Added complete physical build-plate editing for manufacturer, product, shape, dimensions, magnetic/flexible properties, condition, status, preferred materials, temperature limit, and notes.
- Added editable printer hardware details plus Administrator-controlled discovery of Klipper version, Moonraker version, hostname, kinematics, nozzle diameter, and build volume through documented APIs.
- Added the required Size and Hole Calibration step after Retraction, with server-side Horizontal Expansion and Hole Horizontal Expansion calculations and X/Y divergence warnings.

### Changed

- Changed Spoolman synchronization to queue each canonical mutation immediately and run a one-minute safety sweep that imports printer-recorded usage before converging every vendor, filament product, and spool.
- Changed the worker to honor its configured concurrent dispatcher count and reclaim abandoned running jobs after a bounded lock timeout.
- Kept P1-P5 as the initial physical set while allowing later plates and optional B sides to come from same-named saved Moonraker meshes.
- Changed selection, calibration context, dashboard state, and material preferences to record the exact plate side facing up.
- Changed Cura deployment to write one material file rather than quality-change profiles or machine start-G-code patches. The Material Settings and Klipper Settings plugins now consume the material values.
- Changed synchronization to align the selected printer's active physical plate and side with Moonraker while preserving existing physical and side metadata.
- Documented the hash-bound dry-run and commit procedure for importing the initial workbook with one-shot Swarm jobs.
- Changed new filament products to copy a published generic template into an independently tunable draft material profile.
- Changed Cura deployment from one selected profile to the latest published templates and product profiles as one desired-state library. Existing workstations with user materials require explicit Administrator takeover.
- Changed Compose and Swarm upgrades to migrate automatically; a one-shot migration remains only for diagnosis and recovery.
- Changed spool-location ownership so Filament Manager becomes authoritative after import, edit, or explicit clearing and repairs later Spoolman-side drift.
- Changed local username validation to allow two-character usernames and reduced the password minimum from 14 to 10 characters while retaining Argon2id hashing and the existing 256-character maximum.
- Changed calibration from six to seven ordered steps and made published calibration profiles inherit all settings from the selected starting profile before applying calibrated values.
- Changed profile editing to create a new independent draft version, preserving published profile and template revision immutability.
- Changed the workstation agent package version to 0.1.5 so current Arch Linux and Windows testing artifacts identify the matching server release.

### Fixed

- Fixed all filament and spool projections failing against Spoolman 0.23.1 because managed custom fields were undeclared and their values were not JSON-encoded.
- Fixed full reconciliation only reading existing remote spools instead of creating or repairing missing Spoolman vendors, filaments, and spools.
- Fixed metadata reconciliation potentially erasing unimported printer usage by writing canonical remaining weight during routine spool updates.
- Fixed failed, dead, and worker-crash-stranded Spoolman jobs remaining permanently stuck after the integration recovered.
- Fixed the initial `SELECT_BUILD_PLATE` macro state using an unambiguous Python literal so Klipper accepts the macro during startup.
- Fixed double-sided plates and different per-side meshes being impossible to represent.
- Fixed later physical plates being impossible to represent because the database column, JSON contracts, API client, macro, and interface were limited to P1-P5.
- Fixed lexicographic plate ordering that would place P10 before P2.
- Prevented missing Moonraker meshes from deleting or overwriting canonical physical-plate and side details; they are retained and shown as unavailable.
- Fixed web and worker replicas racing database upgrades or requiring the operator to pre-run every schema update.
- Fixed clean Cura installations requiring manual first synchronization and managed Cura material files drifting away from canonical Filament Manager state.
- Fixed routine product, spool, and generic-material setup requiring direct API or Spoolman access.
- Fixed the shipped build-plate macro default to use the explicit quoted `"UNSET"` string and documented how to locate stale included copies.
- Fixed filament color samples being isolated free-text values that could drift between products with the same named color.
- Fixed product-specific Cura settings, full build-plate metadata, and relevant printer information being visible only through limited API or database paths instead of editable application screens.
- Fixed calibration profile publication discarding unmodified settings inherited from a product's generic template.

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
