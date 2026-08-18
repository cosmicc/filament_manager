# Operations

## Routine checks

- `GET /health/live`: process liveness
- `GET /health/ready`: PostgreSQL connectivity and current Alembic revision
- `GET /metrics`: Prometheus request totals and latency
- Diagnostics: running/latest Filament Manager version plus Spoolman, Moonraker, Google, Cura-agent, worker, and synchronization status without secret exposure; **Download log** saves the same bounded overview as text
- Diagnostics queues: pending depth, attempts, dead jobs, and explicit Administrator retry
- Activity: append-only operational and security audit history
- Cura workstations: pairing, detected Cura versions/machines, pre-takeover source selection, and authoritative management controls
- Build Plates: per-side Moonraker mesh checks, newly discovered physical plates/sides, unavailable mappings, and the active loaded side
- Print History: current capture, supported Moonraker history progress, inspection status, unresolved legacy rows, M600 segments, and retained outcome history
- Notifications: unread Moonraker, dead-job, low/empty spool, overdue plate, and failed Cura synchronization conditions

Canonical inventory changes create supported-API Spoolman jobs in the same transaction and dispatch normally begins within one worker polling cycle. Every minute by default, a safety sweep imports printer-recorded usage first and then converges every canonical vendor, filament product, and spool. Every 15 seconds the worker reads Moonraker's supported active Spoolman ID, persistent physical-spool macro state, and exact P-number mesh state. A valid non-null direct selection in an idle/manual-selection phase opens a guarded Fluidd target, and the worker restores Spoolman to the last completed physical boundary until confirmation; other drift is repaired without target capture. The same pass refreshes the bounded Cura/manual-load spool catalog. Every 5 seconds it captures current print state and incrementally reconciles Moonraker history; every 5 minutes it refreshes sanitized printer information. Notification conditions converge every minute. These jobs also seed the configured printer, initial plates, and a missing recommended `Template ASA` for the configured printer/current-nozzle scope. Existing ASA templates are never overwritten. Google publication is scheduled when enabled. External outages create bounded retries and never roll back already committed canonical changes.

The web and worker emit structured console logs for request completion, stable API rejections, validation errors, scheduler and outbox activity, and Moonraker synchronization results. Browser API requests also log their method, path, status, and correlation ID. Error logs include safe messages and tracebacks but never credentials, connection URLs, request bodies, or external response bodies. The Diagnostics text download is a sanitized operational summary rather than a copy of raw process logs; it omits SQL, tracebacks, URLs, credentials, and upstream response content.

## Recovery validation and projection rebuild

Use the **Diagnostics** page for the routine read-only validation report. It checks the current Alembic revision, measurement integrity, stored credential hashes, Spoolman projection consistency, Google publication state, and managed Cura synchronization state, then persists a sanitized result. This validates application recovery readiness; it does not create or restore a PostgreSQL backup.

The same checks are available inside the application container:

```bash
filament-manager-cli verify
```

After restoring canonical PostgreSQL or repairing an external service, an Administrator may use **Rebuild projections** on Diagnostics or run:

```bash
filament-manager-cli rebuild-projections --confirm
```

The rebuild only queues idempotent derived Spoolman, Google, and managed Cura work. It does not alter canonical spool, measurement, profile, plate, nozzle, or print-history records. Continue performing actual database backup and isolated restore through the PostgreSQL platform.

The worker provisions Filament Manager's text custom fields through Spoolman's field API and JSON-encodes each value as required by Spoolman 0.23.1. It paginates complete collections, preserves custom fields owned by other integrations, uses managed UUIDs to avoid duplicate creates, and reclaims jobs abandoned by a terminated worker after `SYNC_OUTBOX_LOCK_TIMEOUT_SECONDS`.

On the first reconciliation after the spool-location ownership migration, a legacy spool with no Filament Manager location adopts its existing non-empty Spoolman location. After that import, or after any location edit in Filament Manager, the canonical free-text value wins and later Spoolman-side edits are repaired automatically.

## Backup set

Back up independently:

1. the canonical `filament_manager` PostgreSQL database;
2. the standalone `spoolman` PostgreSQL database;
3. `docker-stack.yml` and any optional independent stack files in use;
4. an encrypted, access-controlled copy of the private stack-variable inventory;
5. `filament_manager_data` and `spoolman_data` when they contain retained artifacts or logs.
6. workstation-agent backup directories when Cura profile rollback must survive workstation replacement.

Prefer PostgreSQL-native, WAL-aware backups. Retain measurement, usage, audit, and calibration history indefinitely unless policy changes.

## Restore

Restore Filament Manager and Spoolman separately into an isolated environment first. Web and worker startup automatically apply any pending Filament Manager Alembic revision under the migration advisory lock; confirm that succeeds before allowing traffic. If Spoolman must be rebuilt from an empty database, queue canonical projections through the API and then reconcile printer-originated usage. Never copy tables directly between the two databases.

Quarterly, compare spool/product counts, effective weights, profile versions, plates, calibration status, and audit continuity after a full isolated restore.

## Troubleshooting

### Readiness is `schema_unavailable`

Confirm `FILAMENT_MANAGER_DB_*` and `POSTGRES_*` stack variables assemble the intended non-SSL URL for `filament_user`, then inspect the web or worker logs for the automatic-migration result. Do not grant access to the `spoolman` database. Run `alembic current` and `alembic upgrade head` only with the application services stopped when following the recovery procedure below.

The current 0.2.3 schema is `e1f2a3b4c567`. If Diagnostics reports an older revision, first confirm web and worker use the same current image and let automatic migration finish. Never downgrade or manually edit `alembic_version`; use the documented stopped-service recovery procedure if an upgrade genuinely failed.

### Web or worker tasks repeatedly restart after startup

Use the current stack file and image together. The web health check must send the hostname from `FILAMENT_MANAGER_BASE_URL`, and the worker must have its inherited HTTP health check disabled. Do not add a wildcard to `FILAMENT_MANAGER_ALLOWED_HOSTS`; confirm that an explicit list includes the public base-URL hostname.

### Jobs remain pending or fail

Check that the worker service is running, then inspect worker logs, external DNS from the `filament-services` overlay, and the sanitized error class shown in Diagnostics. The Spoolman connection check verifies both API health and managed projection fields. Repair the external service, then allow automatic retry or use Administrator retry for unrelated dead jobs. The 0.1.5 repair migration automatically requeues Spoolman work affected by the former field contract, and the next one-minute sweep projects all existing canonical inventory even when no usable job remains. Corrected 0.2.2 workers normalize long fractional Spoolman weights before comparison and reload printer state after a failed live-print transaction, preventing the repeated `IntegrityError` and `MissingGreenlet` jobs caused by those conditions. Existing dead rows remain durable and require explicit Administrator retry; do not clear them directly in PostgreSQL.

After redeployment, recent worker logs should show `spoolman.reconcile.full` completing. The Diagnostics queue should show new filament/spool upserts completing, and Spoolman should receive existing inventory no later than the next safety sweep when the internal API is reachable.

### Spoolman is unavailable

Verify `http://spoolman:8000/api/v1/health` from the combined Filament Manager stack and the stable LAN endpoint from the printer host. The optional separate-stack layout uses `http://spoolman_spoolman:8000`. Moonraker must not use either Swarm-only hostname.

### Moonraker is unavailable

Confirm `MOONRAKER_BASE_URL` is reachable from the Swarm node and container network. If `MOONRAKER_WEBSOCKET_URL` is empty, Filament Manager derives the same host with `ws` or `wss` and the `/websocket` path. Confirm the configured API key only when Moonraker requires one. In worker logs, inspect `moonraker_active_spool_sync_failed`, `moonraker_build_plate_sync_failed`, or `moonraker_printer_information_sync_failed`; the associated outbox job retries automatically.

### Cura agent has not reported recently

Confirm Cura is closed, then rerun the current workstation-agent installer on the named workstation. The installer identifies an upgrade, preserves pairing and local state, refreshes the service definition, and restarts the service only when it was already running. If Diagnostics still shows the old contact time, inspect the workstation service status and its local logs before pairing a replacement agent.

### Spool workflow does not open or print preflight is blocked

Run `FILAMENT_MANAGER_SPOOL_STATE` in Fluidd. Confirm the integration macro file is included last and the worker log shows `moonraker_spool_preflight_catalog_synchronized` and a one-time `moonraker_spool_preflight_state_initialized`. A missing Cura print candidate means Cura has stale material settings, a `Template <material type>` entry was selected, no eligible projected spool remains, or the product lacks a current exact profile for the configured printer/nozzle. Synchronize the Cura workstation and resend the sliced file after correcting inventory/profile readiness.

If Klipper reports that `variable_catalog_revision` is not a valid literal during startup, replace the installed macro reference with the current `integrations/klipper/filament-manager-macros.cfg`. The current reference uses a non-empty initialization sentinel so config editors cannot collapse the value; the worker replaces it with the real catalog revision after startup.

Keep Fluidd's **Show spool selection dialog on print start** disabled. Run `LOAD_FILAMENT` or `FILAMENT_MANAGER_LOAD_TARGET` without parameters for the managed manual-load chooser. It accepts a projected non-empty spool with a safe temperature from its latest exact non-archived profile or linked in-scope template; it does not weaken Cura's current exact-profile requirement. If this chooser is empty, confirm the spool has reached Spoolman, has remaining mass, and has one of those temperature sources. A non-null direct Spoolman selection made while idle or while M600 is waiting becomes a guarded Fluidd target within the next 15-second state pass; the worker still restores the persisted physical ID until the operator explicitly adopts an already-loaded spool or completes motion. A direct clear, invalid target, or selection during another phase is repaired without changing canonical state.

Diagnostics shows the running version and compares it with the highest non-draft semantic GitHub release, including testing prereleases. The fixed public lookup is cached for 15 minutes. An unavailable result is informational about the check itself; it does not indicate that the application or database is unhealthy.

During a change, `unloading` retains the old active ID, `inserting` means no active spool, and `loading` still means no active spool. `ready` means the exact new ID has been committed. `load_select` and `manual_select` are recoverable chooser phases: rerun `FILAMENT_MANAGER_LOAD_TARGET` to reopen the prompt. A ten-minute insertion timeout turns off the nozzle and retains the last completed boundary. Use the prompt's cancel action or `FILAMENT_MANAGER_ABORT` after a macro error; never invoke the internal `_FILAMENT_MANAGER_RECORD_LOADED` helper manually.

For a **G-code Blocked** prompt, open the matching Print History row. A listed mismatch requires correcting the current profile, allowing synchronization, and reslicing. An unavailable result means Moonraker could not supply the file or its exact managed profile could not be resolved; do not bypass it by changing Spoolman manually. Administrators may return to the recommended warning policy during diagnosis, but the setting change is audited and synchronized to Klipper.

### Print history is missing or duplicated

Inspect the `moonraker.print_history.reconcile` outbox job and `moonraker_print_history_*` worker log events. The configured default is `MOONRAKER_PRINT_INTERVAL_SECONDS=5`. Filament Manager uses Moonraker's supported current `print_stats`, history list, file metadata, and G-code download surfaces; connection or authorization errors retry without inventing exact state. Pre-0.2.1 jobs intentionally show as legacy/unresolved when spool/profile context is unavailable.

### A saved build-plate side mesh does not appear

Confirm the mesh is saved in Klipper as exact `P<number>` for Side A or `P<number>b` for Side B, such as `P6` or `P6b`. An Operator may use **Add Side B** before calibration, but it intentionally remains unavailable until Moonraker reports that exact lowercase-b mesh. `P0`, `P01`, uppercase `B`, lowercase plate names, and descriptive profiles are intentionally ignored. Wait for the next 15-second automatic state pass, then confirm Klippy is ready and that Moonraker returns the `bed_mesh` object from `/printer/objects/query`. Inspect the worker log and the `moonraker.state.reconcile` job when the page remains stale.

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

### A service stops during automatic database migration

Inspect both web and worker logs for `database_migration_started`, `database_migration_completed`, a lock timeout, or an Alembic error. Do not disable automatic migration and start the application against an older schema. Keep the application stopped, correct the database or migration problem, take a fresh backup if appropriate, and run the documented one-shot recovery migration. The database URL is intentionally never included in migration logs.

### A Cura material imports without some settings

The workstation reports only the approved settings exposed by the configured Material Settings catalog. Unsupported keys and machine start G-code are intentionally discarded. Confirm the current Material Settings and Klipper Settings plugins are installed and the desired settings are stored on the Cura material, then let the agent heartbeat again before importing.

### A managed Cura edit does not appear

Confirm Cura is closed so its material file is complete, the workstation is under authoritative management, and the edited entry was originally synchronized by Filament Manager. The agent accepts setting changes only from a known deterministic managed GUID. New or copied Cura materials and metadata-only edits are intentionally ignored. After the next heartbeat, reload the linked Template or Filament detail page; the accepted change saves directly and the current library synchronizes automatically.

### A filament did not inherit a template change

Reload the filament detail and confirm whether that specific key is marked customized. Explicit customizations intentionally remain unchanged; every other value inherits immediately from the template save. Use **Reset to Template** for a key that should return to inherited ownership, then allow automatic Cura synchronization.

### A workstation is paired but Cura profiles never appear

Check the workstation's agent service log first. If it reports `CERTIFICATE_VERIFY_FAILED` even though the Filament Manager private CA is trusted by the operating system, upgrade the workstation agent to the current 0.2.3 package. The corrected agent uses the verified operating-system TLS context for pairing and every service request. Do not disable certificate verification. After restart, confirm that Diagnostics shows a current contact time, then reopen the takeover mapping dialog.

### Cura synchronization fails during file replacement

The agent restores the pre-synchronization backup automatically. Review the sanitized synchronization error and local structured agent log. Use `filament-manager-agent rollback DEPLOYMENT_UUID` for an explicit restoration when required. After authoritative management is enabled, do not create or copy user material files directly in Cura because heartbeat synchronization will restore Filament Manager's desired state.

## Recovery objectives

Define formal RPO/RTO values with the central PostgreSQL operator. Printer continuity prioritizes Spoolman availability; full inventory, calibration, and audit integrity depends on the canonical Filament Manager backup.
