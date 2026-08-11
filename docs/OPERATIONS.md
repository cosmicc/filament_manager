# Operations

## Routine checks

- `GET /health/live`: process liveness
- `GET /health/ready`: PostgreSQL connectivity and current Alembic revision
- `GET /metrics`: Prometheus request totals and latency
- Integrations: Spoolman, Moonraker, and Google status without secret exposure
- Projection jobs: pending depth, attempts, dead jobs, and explicit Administrator retry
- Activity: append-only operational and security audit history
- Cura workstations: last contact, detected Cura versions/machines, scoped credential state, deployment attempts, and warnings

Workers schedule supported-API Spoolman reconciliation at the configured interval. Google publication is also scheduled when enabled. External outages create bounded retries and never roll back already committed canonical changes.

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

Restore Filament Manager and Spoolman separately into an isolated environment first. Apply the matching Alembic revision before starting the web service. If Spoolman must be rebuilt from an empty database, queue canonical projections through the API and then reconcile printer-originated usage. Never copy tables directly between the two databases.

Quarterly, compare spool/product counts, effective weights, profile versions, plates, calibration status, and audit continuity after a full isolated restore.

## Troubleshooting

### Readiness is `schema_unavailable`

Confirm `FILAMENT_MANAGER_DB_*` and `POSTGRES_*` stack variables assemble the intended URL for `filament_manager_user`, then run `alembic current` and `alembic upgrade head`. Do not grant access to the `spoolman` database.

### Jobs remain pending or fail

Check worker logs, external DNS from the `filament-services` overlay, and the sanitized error class shown in Integrations. Repair the external service, then allow automatic retry or use Administrator retry for dead jobs.

### Spoolman is unavailable

Verify `http://spoolman:8000/api/v1/health` from the combined Filament Manager stack and the stable LAN endpoint from the printer host. The optional separate-stack layout uses `http://spoolman_spoolman:8000`. Moonraker must not use either Swarm-only hostname.

### Moonraker is unavailable

Confirm `MOONRAKER_BASE_URL` is reachable from the Swarm node and container network. If `MOONRAKER_WEBSOCKET_URL` is empty, Filament Manager derives the same host with `ws` or `wss` and the `/websocket` path. Confirm the configured API key only when Moonraker requires one.

### A manual weight increases remaining mass

Confirm the selected spool, scale zero, gross value, and stored tare. The application requires a second confirmation above configured tolerance and an Administrator override above nominal capacity. Do not alter historical usage events.

### Workbook import is rejected

The dry run is tied to the exact SHA-256 file. Resolve row errors or select the unchanged approved file. Import is intentionally refused when canonical spool inventory is not empty.

### Cura deployment remains pending

Confirm the per-user systemd service or Windows logon task is running and its last-contact time is current. Close Cura; the agent deliberately defers all writes while any Cura process is open. Run `filament-manager-agent scan` under the Cura user and confirm the expected version, machine name, and nozzle are detected.

### Material installs but pressure advance reports a warning

The matched machine inherits its start G-code and has no local `machine_start_gcode` override. Save a machine start-G-code customization once in Cura, close Cura, and deploy the next profile revision. The agent will then insert or replace only its delimited pressure-advance block without discarding the rest of the G-code.

### A Cura deployment fails during file replacement

The agent restores the pre-deployment backup automatically. Review the sanitized deployment error and local structured agent log. Do not manually delete unmanaged Cura files. Use `filament-manager-agent rollback DEPLOYMENT_UUID` for an explicit restoration when required.

## Recovery objectives

Define formal RPO/RTO values with the central PostgreSQL operator. Printer continuity prioritizes Spoolman availability; full inventory, calibration, and audit integrity depends on the canonical Filament Manager backup.
