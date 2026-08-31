# Operations

## Routine checks

- `GET /health/live`: process liveness
- `GET /health/ready`: PostgreSQL connectivity and current Alembic revision
- `GET /metrics`: Prometheus request totals and latency
- Diagnostics: running/latest Filament Manager version plus Spoolman, Moonraker, Google, Cura-agent, exact per-installation Material Settings exposure, worker, and synchronization status without secret exposure; immutable validation summaries display every check they count, retained failures are labelled as history when no longer current, and **Download log** saves the same bounded overview as text
- Diagnostics queues: actionable pending/running/failed/dead summaries and latest sanitized failure per job type; individual Projection operations / Recent jobs are intentionally not displayed, while superseded recurring history remains retained without counting as queue debt
- Activity: append-only operational and security audit history
- Cura workstations: pairing, detected Cura versions/machines, pre-takeover source selection, authoritative management controls, and exact-version recovery points
- Dashboard: one live 10-second snapshot led by the full-width printer status card with three inventory value cards directly beneath it, covering Moonraker/Klipper state, active spool, active plate, inventory totals, bounded print progress and filename, and available nozzle, bed, and chamber temperatures; an unavailable printer degrades this card without blocking inventory
- Build Plates: per-side Moonraker mesh checks, newly discovered physical plates/sides, unavailable mappings, and the active loaded side
- Print History: current capture, browser-safe server-side 10/25/50/100 pagination, retryable request failures distinct from a genuine empty history, supported Moonraker history progress and exact terminal reasons, inspection status, unresolved legacy rows, M600 segments, and retained outcome history
- Notifications: unread Moonraker, dead-job, low/empty spool, overdue plate, and newest operation-scoped failed Cura synchronization conditions in an outside-click-dismissible panel; named backup-request failures remain visible in Recovery points without creating duplicate synchronization alerts

Canonical inventory changes create supported-API Spoolman jobs in the same transaction and dispatch normally begins within one worker polling cycle. Every minute by default, a safety sweep imports printer-recorded usage first and then converges every canonical vendor, filament product, and spool. Every 5 seconds the worker reads Moonraker's supported active Spoolman ID, persistent physical-spool macro state, and exact P-number mesh state. A valid non-null direct selection in an idle/manual-selection phase opens a guarded Fluidd target, and the worker restores Spoolman to the last completed physical boundary until confirmation; other drift is repaired without target capture. The same pass refreshes the bounded Cura/manual-load spool catalog. A failed periodic pass retries no later than its configured interval, so active-spool recognition remains inside one minute while Moonraker is reachable. Every 5 seconds it captures current print state and incrementally reconciles Moonraker history; a malformed bounded legacy record is skipped without blocking valid records or the successful-pass checkpoint. Every 5 minutes it refreshes sanitized printer information. Notification conditions converge every minute. These jobs also seed the configured printer, initial plates, and a missing recommended `Template ASA` for the configured printer/current-nozzle scope. Existing ASA templates are never overwritten. Google publication is scheduled when enabled. External outages create bounded retries and never roll back already committed canonical changes.

The web and worker emit structured console logs for request completion, stable API rejections, validation errors, scheduler and outbox activity, and Moonraker synchronization results. Browser API requests also log their method, path, status, and correlation ID. Error logs include safe messages and tracebacks but never credentials, connection URLs, request bodies, or external response bodies. The Diagnostics text download is a sanitized operational summary rather than a copy of raw process logs; it omits SQL, tracebacks, URLs, credentials, and upstream response content.

## Recovery validation and projection rebuild

Use the **Diagnostics** page for the routine read-only validation report. It checks the current Alembic revision, measurement integrity, stored credential hashes, Spoolman projection consistency, Google publication state, managed Cura synchronization state, and Cura recovery readiness, then persists a sanitized result. This validation remains read-only and separate from the canonical database snapshot controls at the bottom of Diagnostics.

The same checks are available inside the application container:

```bash
filament-manager-cli verify
```

After restoring canonical PostgreSQL or repairing an external service, an Administrator may use **Rebuild projections** on Diagnostics or run:

```bash
filament-manager-cli rebuild-projections --confirm
```

The rebuild only queues idempotent derived Spoolman, Google, and managed Cura work. It does not alter canonical spool, measurement, profile, plate, nozzle, or print-history records.

## Canonical database snapshots

The worker creates a compressed Filament Manager PostgreSQL snapshot every 24 hours by default. Administrators may change the interval, enable/disable scheduling, and change automatic retention on Diagnostics; the default keeps the newest ten automatic archives. The runtime uses PostgreSQL client 18 for PostgreSQL 18 and older supported-server dumps. Dump creation waits until no canonical print is in progress. A failed automatic backup records its failure count and next retry, beginning at fifteen minutes and doubling to a six-hour maximum instead of retrying every worker minute. Manual and imported archives are not pruned by automatic retention. Each ZIP contains exactly a PostgreSQL custom-format dump and a versioned manifest with size and SHA-256 evidence. Archives are written atomically with private permissions under `/data/database-backups`.

Administrators may create a snapshot immediately, download any validated ZIP, or import a trusted ZIP downloaded from this or another Filament Manager installation. Import validates archive paths, member count, encryption state, bounded sizes, PostgreSQL custom-dump identity, manifest metadata, and checksums before retaining it. These checks detect corruption and malformed archives; they are not a third-party authenticity signature, so import only trusted Filament Manager downloads.

Selecting **Restore** and typing `RESTORE` writes a private exact-archive request. It never restores the live database. Stop web and worker, run the stack's zero-replica `database-restore` service once, and confirm success before restarting them. The command makes a manual pre-restore safety archive, runs a clean restore inside one PostgreSQL transaction without restoring ownership or ACLs, applies forward migrations, records the recovery, and revokes every restored browser session. A failed restore leaves the request available and application services must remain stopped until recovery is resolved. Exact Swarm and Compose commands are in `INSTALL.md`.

The worker provisions Filament Manager's text custom fields through Spoolman's field API and JSON-encodes each value as required by Spoolman 0.23.1. Structured display palettes are serialized to an inner compact JSON string before that outer encoding so the field still validates as text. It paginates complete collections, preserves custom fields owned by other integrations, uses managed UUIDs to avoid duplicate creates, and reclaims jobs abandoned by a terminated worker after `SYNC_OUTBOX_LOCK_TIMEOUT_SECONDS`.

On the first reconciliation after the spool-location ownership migration, a legacy spool with no Filament Manager location adopts its existing non-empty Spoolman location. After that import, or after any location edit in Filament Manager, the canonical free-text value wins and later Spoolman-side edits are repaired automatically.

## Backup set

Back up independently:

1. the canonical `filament_manager` PostgreSQL database, including downloaded application-created ZIPs stored outside the application volume for host-loss recovery;
2. the standalone `spoolman` PostgreSQL database;
3. `docker-stack.yml` and any optional independent stack files in use;
4. an encrypted, access-controlled copy of the private stack-variable inventory;
5. `filament_manager_data` and `spoolman_data` when they contain retained artifacts or logs.
6. workstation-agent backup directories when local Cura deployment or pre-recovery rollback must survive workstation replacement.

Application ZIPs provide convenient point-in-time logical recovery but are not sufficient for loss of the Docker volume or PostgreSQL host when they remain on that same host. Download or replicate them to separate protected storage and retain PostgreSQL-native, WAL-aware platform backups for stronger recovery coverage. Retain measurement, usage, audit, and calibration history indefinitely unless policy changes.

## Restore

Restore Filament Manager and Spoolman separately into an isolated environment first whenever practical. For an application ZIP, use the prepared stopped-service restore workflow; never run `pg_restore` while web or worker is live. Web and worker startup automatically apply any pending Filament Manager Alembic revision under the migration advisory lock; confirm that succeeds before allowing traffic. If Spoolman must be rebuilt from an empty database, queue canonical projections through the API and then reconcile printer-originated usage. Never copy tables directly between the two databases.

Quarterly, compare spool/product counts, effective weights, profile versions, plates, calibration status, and audit continuity after a full isolated restore.

## Troubleshooting

### Filaments disappear after selecting Rainbow

Version 0.5.3 could commit the fixed six-sample Rainbow palette and then reject its own three-sample response contract. The canonical filament, template, and profile rows were not deleted, but that one response error made the complete filament collection unavailable and caused Print settings to show `Unknown filament`. Upgrade the web and worker services to 0.5.4 or newer; the corrected response contract restores the existing records without a database rollback. Version 0.5.5 additionally prevents a later Rainbow product edit from resubmitting that fixed six-sample response palette through the three-sample multicolor request contract. Continue protecting all canonical work with the PostgreSQL-native backups listed above; Cura recovery points protect workstation configuration, not the canonical database.

### Readiness is `schema_unavailable`

Confirm `FILAMENT_MANAGER_DB_*` and `POSTGRES_*` stack variables assemble the intended non-SSL URL for `filament_user`, then inspect the web or worker logs for the automatic-migration result. Do not grant access to the `spoolman` database. Run `alembic current` and `alembic upgrade head` only with the application services stopped when following the recovery procedure below.

The current 0.5.8 schema remains `a9b0c1d2e345`. If Diagnostics reports an older revision, first confirm web and worker use the same current image and let automatic migration finish. The migration introduced in 0.5.7 backfills every profile's initial-layer build-plate temperature from its regular build-plate temperature and adds bounded stored print-thumbnail fields. Never downgrade or manually edit `alembic_version`; use the documented stopped-service recovery procedure if an upgrade genuinely failed.

### Web or worker tasks repeatedly restart after startup

Use the current stack file and image together. The web health check must send the hostname from `FILAMENT_MANAGER_BASE_URL`, and the worker must have its inherited HTTP health check disabled. Do not add a wildcard to `FILAMENT_MANAGER_ALLOWED_HOSTS`; confirm that an explicit list includes the public base-URL hostname.

### Jobs remain pending or fail

Check that the worker service is running, then inspect worker logs, external DNS from the `filament-services` overlay, and the latest sanitized cause for each failing job type in Diagnostics. The Projection Queue is the PostgreSQL transactional outbox that durably delivers committed canonical changes to Spoolman, Moonraker, Google, and Cura. A short-lived pending row is normal; a pending row with attempts is a scheduled retry, and Diagnostics shows its retry count and next-attempt time. Repair the external service, then allow automatic retry or use Administrator retry for unrelated dead jobs. Version 0.3.3 expands outbox aggregate versions to `BIGINT`, retires old manual recurring failures once the normal recurring operation recovers, and coalesces/retries each spool's newest weight correction through Spoolman's supported net `remaining_weight` update. Superseded rows remain durable history but are excluded from actionable Diagnostics counts. Do not delete queue history directly in PostgreSQL.

After redeployment, recent worker logs should show `spoolman.reconcile.full` completing. The Diagnostics queue should show new filament/spool upserts completing, and Spoolman should receive existing inventory no later than the next safety sweep when the internal API is reachable. The projection-consistency check clears when the new acknowledgements are recorded. Any remaining actionable Spoolman failure has its own representative cause in **Latest cause by job type** and the downloaded log; it can no longer be hidden by a busier Moonraker failure. A current `moonraker.state.reconcile` failure names the bounded failing physical-state sub-operation. Spool-preflight catalog publication is reported separately per printer and no longer fails an otherwise successful state pass. Verify the checked-in current Klipper macro include and `save_variables` configuration when that catalog check is not healthy.

### Bugsnag receives no reports or performance spans

Confirm `BUGSNAG_ENABLED=true`, the deployment `BUGSNAG_API_KEY` is the 32-character SDK API key, and the same variables reach both web and worker. Browser performance also requires `BUGSNAG_BROWSER_PERFORMANCE_ENABLED=true`. Set `BUGSNAG_RELEASE_STAGE=production` for the production deployment; arbitrary safe custom stages are accepted, so a misspelling such as `productiom` is reported exactly as configured. Inspect `/runtime-config.js` only from the authenticated deployment network and confirm the enabled flags; the SDK key is expected to be browser-visible. Permit outbound HTTPS to `notify.bugsnag.com` and the key-specific `<key>.otlp.bugsnag.com` performance host. Browser error-session reporting is intentionally disabled. A delivery outage must not make Filament Manager unhealthy.

Readable minified browser frames additionally require the separate Upload API key in the protected GitHub Actions repository secret `BUGSNAG_UPLOAD_API_KEY` before a direct `main` push builds the image. Pull requests and non-`main` pushes intentionally skip source-map upload. Do not trigger a real production exception merely to test reporting; use a controlled testing deployment and then confirm that the Bugsnag event contains only generic messages, normalized paths, and the documented bounded metadata.

### Spoolman is unavailable

Verify `http://spoolman:8000/api/v1/health` from the combined Filament Manager stack and the stable LAN endpoint from the printer host. The optional separate-stack layout uses `http://spoolman_spoolman:8000`. Moonraker must not use either Swarm-only hostname.

### Moonraker is unavailable

Confirm `MOONRAKER_BASE_URL` is reachable from the Swarm node and container network. If `MOONRAKER_WEBSOCKET_URL` is empty, Filament Manager derives the same host with `ws` or `wss` and the `/websocket` path. Confirm the configured API key only when Moonraker requires one. In worker logs, inspect `moonraker_active_spool_sync_failed`, `moonraker_build_plate_sync_failed`, or `moonraker_printer_information_sync_failed`; the associated outbox job retries automatically.

### Cura agent has not reported recently

Confirm Cura is closed, then rerun the current workstation-agent installer on the named workstation. The installer identifies an upgrade, preserves pairing and local state, refreshes the service definition, and restarts the service only when it was already running. If Diagnostics still shows the old contact time, inspect the workstation service status and its local logs before pairing a replacement agent.

### Spool workflow does not open or print preflight is blocked

Run `FILAMENT_MANAGER_SPOOL_STATE` in Fluidd. Confirm the integration macro file is included last and the worker log shows `moonraker_spool_preflight_catalog_synchronized` and a one-time `moonraker_spool_preflight_state_initialized`. A missing Cura print candidate means Cura has stale material settings, a `Template <material type>` entry was selected, no eligible projected spool remains, or the product lacks a current exact profile for the configured printer/nozzle. Synchronize the Cura workstation and resend the sliced file after correcting inventory/profile readiness.

If Fluidd remains on **Inspecting G-code** with only **Cancel Print** available, cancel that held print and upgrade the Filament Manager web and worker services to 0.6.4 or newer before resending it. Current workers retry a persisted fail-closed inspection decision on each ten-second print pass while Klipper still reports the blocking gate, so a split state read or transient Moonraker acknowledgement failure recovers automatically.

If Klipper reports that `variable_catalog_revision` is not a valid literal during startup, replace the installed macro reference with the current `integrations/klipper/filament-manager-macros.cfg`. The current reference uses a non-empty initialization sentinel so config editors cannot collapse the value; the worker replaces it with the real catalog revision after startup.

Keep Fluidd's **Show spool selection dialog on print start** disabled. Run `LOAD_FILAMENT` or `FILAMENT_MANAGER_LOAD_TARGET` without parameters for the managed manual-load chooser. It accepts a projected non-empty spool with a safe temperature from its latest exact non-archived profile or linked in-scope template; it does not weaken Cura's current exact-profile requirement. If this chooser is empty, confirm the spool has reached Spoolman, has remaining mass, and has one of those temperature sources. A non-null direct Spoolman selection made while idle or while M600 is waiting becomes a guarded Fluidd target within the next 10-second idle state pass; the worker still restores the persisted physical ID until the operator explicitly adopts an already-loaded spool or completes motion. A direct clear, invalid target, or selection during another phase is repaired without changing canonical state.

Diagnostics shows the running version and compares it with the highest non-draft semantic GitHub release, including testing prereleases. The fixed public lookup is cached for 15 minutes. An unavailable result is informational about the check itself; it does not indicate that the application or database is unhealthy.

During a change, `unloading` retains the old active ID, `inserting` means no active spool, and `loading` still means no active spool. `ready` means the exact new ID has been committed. `load_select` and `manual_select` are recoverable chooser phases: rerun `FILAMENT_MANAGER_LOAD_TARGET` to reopen the prompt. A ten-minute insertion timeout turns off the nozzle and retains the last completed boundary. Use the prompt's cancel action or `FILAMENT_MANAGER_ABORT` after a macro error; never invoke the internal `_FILAMENT_MANAGER_RECORD_LOADED` helper manually.

For a **G-code Blocked** prompt, open the matching Print History row. A listed mismatch requires correcting the current profile, allowing synchronization, and reslicing. An unavailable result means Moonraker could not supply the file or its exact managed profile could not be resolved; do not bypass it by changing Spoolman manually. Administrators may return to the recommended warning policy during diagnosis, but the setting change is audited and synchronized to Klipper.

### A print stops after the purge line and Fluidd shows paused at 0%

Replace the exact installed file named by the active `[include ...]` with the current `filament-manager-macros.cfg` reference, confirm it is still included last, and issue `FIRMWARE_RESTART` while the printer is idle. An older installation may call that file `filament-manager_macros.cfg`; do not leave that underscore-named file active while uploading the corrected hyphen-named copy beside it. Run `FILAMENT_MANAGER_SPOOL_STATE` in the Fluidd console and confirm its response contains `macro=0.6.7`. An absent or older version proves that Klipper loaded another copy. Older references pause the Cura virtual-SD stream with `M25` but incorrectly require `virtual_sdcard.is_active` before sending its matching `M24`; Klipper makes that property false while the file is paused. Version 0.6.7 also bounds an unmet release-state retry to one attempt every half second for thirty seconds before it shows Retry and Cancel. This also explains why the normal `RESUME` command reports that the printer is not paused: `RESUME` tracks the separate `PAUSE` command.

If cancellation is already stuck and the Klipper console is available, issue `SDCARD_RESET_FILE` to unload the retained file and reset its print state. Do not use `M24` after printer power, position, homing, or thermal state has been lost; it would continue the old file from the retained position. Restart the print only after installing the corrected reference and verifying its version. The current reference retains an app-owned resume latch, respects a real operator pause, completes any deferred build-plate continuation, cancels the delayed release, and explicitly resets an orphaned direct-`M25` hold before calling the printer's original cancellation cleanup.

### Print history is missing or duplicated

Inspect the `moonraker.print_history.reconcile` outbox job and `moonraker_print_history_*` worker log events. The configured default is `MOONRAKER_PRINT_INTERVAL_SECONDS=10`. Filament Manager captures supported current `print_stats` and preflight macro state in one combined query on every pass, postpones the complete history-list download while printing or paused, and imports it when the printer reaches a terminal state. Connection or authorization errors retry without inventing exact state. Pre-0.2.1 jobs intentionally show as legacy/unresolved when spool/profile context is unavailable.

### Klipper reports `MCU 'mcu' shutdown: Timer too close`

Treat this as a printer-host scheduling failure, not a safe print completion. Check host CPU load, swap pressure, storage errors, thermal throttling, voltage warnings, and competing services before issuing `FIRMWARE_RESTART`. Version 0.6.7 reduces avoidable Filament Manager activity during motion: current print and preflight state share one ten-second query, complete Moonraker history is deferred, active-spool/mesh/catalog and printer-information reads are deferred, the virtual-SD release loop is bounded, and PostgreSQL dumps are deferred with failure backoff. A stale in-progress row left by this kind of MCU shutdown no longer blocks future manual or automatic backups after a minimal Moonraker query confirms terminal state. If the error recurs after upgrading both the application and installed macro reference, preserve `klippy.log` plus worker logs around the same timestamp and compare host load; do not automatically resume the interrupted file after position or thermal state may have been lost.

### A saved build-plate side mesh does not appear

Confirm the mesh is saved in Klipper as exact `P<number>` for Side A or `P<number>b` for Side B, such as `P6` or `P6b`. An Operator may use **Add Side B** before calibration, but it intentionally remains unavailable until Moonraker reports that exact lowercase-b mesh. `P0`, `P01`, uppercase `B`, lowercase plate names, and descriptive profiles are intentionally ignored. Wait for the next 10-second automatic idle-state pass, then confirm Klippy is ready and that Moonraker returns the `bed_mesh` object from `/printer/objects/query`. Inspect the worker log and the `moonraker.state.reconcile` job when the page remains stale.

Run `SELECT_BUILD_PLATE` without `PLATE=` to inspect the live Fluidd list from `printer.bed_mesh.profiles`. The chooser requires no static per-plate helper macros and filters out every invalid profile name.

Synchronization never deletes canonical plates or sides or overwrites their descriptive and maintenance metadata. A previously known side is marked unavailable when its same-named mesh is missing. If Moonraker has a valid plate-side mesh loaded, that physical plate and side become active for the selected printer.

### Klipper rejects `variable_active_plate` during startup

Install the current `integrations/klipper/filament-manager-macros.cfg` and confirm the macro declares `variable_active_plate: "UNSET"`. Klipper parses every `variable_` value as a Python literal; a blank value is invalid and strings require quotes. On the Klipper host, run `grep -Rns --include='*.cfg' 'variable_active_plate' ~/printer_data/config` to find stale or duplicate copies. Correct every included occurrence, then issue `RESTART`.

### A Spoolman bucket does not appear in Filament Manager

Only a legacy spool whose canonical location has never been established imports a remote bucket. Run the Administrator Spoolman reconciliation action and check for a `spool.location.import` audit event. Once imported or locally edited, change the free-text location from the Filament Manager Spools page; later edits made directly in Spoolman are intentionally overwritten.

### A manual weight increases remaining mass

Confirm the selected spool, scale zero, gross value, and stored tare. The application requires a second confirmation above configured tolerance and an Administrator override above nominal capacity. Do not alter historical usage events.

### Workbook import is rejected

The dry run is tied to the exact SHA-256 file. Resolve row errors or select the unchanged approved file. Import is intentionally refused when canonical spool inventory is not empty.

### Cura synchronization remains pending

Confirm the per-user systemd service or Windows logon task is running and its last-contact time is current. Close Cura; the agent deliberately defers all writes while any Cura process is open. Run `filament-manager-agent scan` under the Cura user and confirm the expected version, machine name, and nozzle are detected.

### Cura was reset or must be rebuilt

Deploy the updated server and allow schema `a9b0c1d2e345` to migrate before upgrading the workstation agent; a 0.6.7 agent is required for synchronized version reporting, meaningful filler-qualified Cura product labels that omit empty or `None` filler values, clean Cura quality-profile ownership, the 54-key Material Settings contract, separate regular/initial bed-temperature boundaries, recurring exact linked-extruder nozzle verification, interactive Windows installation, and cross-workstation recovery behavior. For routine protection, leave the agent running and close Cura periodically. A healthy configuration containing at least one printer is captured automatically, and an Administrator can queue a named backup from Cura Workstations. The fifteen newest automatic points per installation/version are retained; named points do not consume that quota and remain until explicit deletion. Saved points are listed before recent capture-request history; a failed named request remains historical there and does not mark the connected agent unhealthy. A deleted automatic point stays suppressed until the configuration changes or an Administrator explicitly requests a named capture. A missing-printer or large-deletion capture is blocked so it cannot displace the last known-good point.

For recovery, install or reset the same Cura version, open it once, sign in to the Cura account, wait for the account-managed plugins to install, then close Cura completely. On **Cura Workstations**, choose **Restore Cura setup**, select and review the exact-version point, and confirm. Leave Cura closed until the workstation status returns to **Ready**. Safe Cura2Moonraker behavior choices are merged into the current local instance while its current URL and API key remain untouched; re-enter excluded credentials only if the reset Cura installation no longer has them. Filament Manager restores the bounded non-sensitive printer/extruder configuration—including start/end G-code and safe machine options—plus custom profile state and safe preferences. It then realigns Cura's extruder nozzle to the app's current physical nozzle before synchronizing canonical materials. It records plugin names and versions for verification but never installs plugin binaries.

If recovery reports failure, inspect the workstation's local structured log. On Arch Linux use `journalctl --user -u filament-manager-agent.service --since today --no-pager`; on Windows review the latest **Filament Manager Cura Agent** scheduled-task output. The agent restores its pre-recovery archive automatically after a write failure and reports only a bounded path-free reason to the server. Account sessions, credentials, URLs, paths, and plugin code are intentionally absent from server snapshots. Cura's key-only setting-visibility preset syntax is supported; a current agent no longer rejects those valid files as malformed configuration.

### A service stops during automatic database migration

Inspect both web and worker logs for `database_migration_started`, `database_migration_completed`, a lock timeout, or an Alembic error. Do not disable automatic migration and start the application against an older schema. Keep the application stopped, correct the database or migration problem, take a fresh backup if appropriate, and run the documented one-shot recovery migration. The database URL is intentionally never included in migration logs.

### A Cura material imports without some settings

The workstation reports only the approved settings exposed by the configured Material Settings catalog. Unsupported keys and machine start G-code are intentionally discarded. Confirm the current Material Settings and Klipper Settings plugins are installed and the desired settings are stored on the Cura material, then let the agent heartbeat again before importing.

### Cura material print settings are waiting or incomplete

Upgrade the workstation agent, allow the current managed library deployment to finish while Cura is closed, then open Cura once with the configured printer active. Cura Workstations should report **54 of 54 verified**. A waiting state means the current plugin has not yet produced a receipt for the deployed catalog. An error lists bounded missing keys and shows whether Material Settings and Klipper Settings are ready. Install or enable the named plugin, restart Cura, and recheck; do not manually remove keys from the plugin selection because Filament Manager will restore its authoritative list.

### A managed Cura edit does not appear

Confirm Cura is closed so its material file is complete, the workstation is under authoritative management, and the edited entry was originally synchronized by Filament Manager. The agent accepts setting changes only from a known deterministic managed GUID. New or copied Cura materials and metadata-only edits are intentionally ignored. After the next heartbeat, reload the linked Template or Filament detail page; the accepted change saves directly and the current library synchronizes automatically.

### A filament did not inherit a template change

Reload the filament detail and confirm whether that specific key is marked customized. Explicit customizations intentionally remain unchanged; every other value inherits immediately from the template save. Use **Reset to Template** for a key that should return to inherited ownership, then allow automatic Cura synchronization.

### A workstation is paired but Cura profiles never appear

Check the workstation's agent service log first. If it reports `CERTIFICATE_VERIFY_FAILED` even though the Filament Manager private CA is trusted by the operating system, upgrade the workstation agent to version 0.3.3 or newer. The corrected agent uses the verified operating-system TLS context for pairing and every service request. Do not disable certificate verification. After restart, confirm that Diagnostics shows a current contact time, then reopen the takeover mapping dialog.

### Cura synchronization fails during file replacement

The agent restores the pre-synchronization backup automatically. Review the sanitized synchronization error and local structured agent log. Use `filament-manager-agent rollback DEPLOYMENT_UUID` for an explicit restoration when required. After authoritative management is enabled, do not create or copy user material files directly in Cura because heartbeat synchronization will restore Filament Manager's desired state.

## Recovery objectives

Define formal RPO/RTO values with the central PostgreSQL operator. Printer continuity prioritizes Spoolman availability; full inventory, calibration, and audit integrity depends on the canonical Filament Manager backup.
