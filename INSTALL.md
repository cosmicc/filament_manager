# Install Filament Manager

Use Docker Compose for a local workshop installation. The production `docker-stack.yml` deploys Filament Manager, its worker, and Spoolman together and assumes an existing remote PostgreSQL server.

## Local Docker Compose

Requirements: Docker Engine with Compose, `openssl`, and ports `8080` and `7912` available.

1. Create a private deployment-variable file from the template:

   ```bash
   cp .env.example .env
   chmod 600 .env
   openssl rand -hex 32       # Generate each database password separately.
   ```

   Replace every `replace_with_...` value in `.env`. Use a different generated value for `POSTGRES_ADMIN_PASSWORD`, `FILAMENT_MANAGER_DB_PASSWORD`, and `SPOOLMAN_DB_PASSWORD`. For local HTTP access, set `FILAMENT_MANAGER_BASE_URL=http://localhost:8080`, `FILAMENT_MANAGER_ALLOWED_HOSTS=localhost,127.0.0.1`, `FILAMENT_MANAGER_SECURE_COOKIES=false`, and `SPOOLMAN_PUBLIC_URL=http://localhost:7912`. Set the one printer's Moonraker ID, name, URL, and nozzle diameter. The ignored `.env` file contains credentials; never commit it.

2. Build and start PostgreSQL, Spoolman, Filament Manager, and its worker:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml build
   docker compose --env-file .env -f docker/docker-compose.yml up -d
   ```

   The web and worker both check for pending Alembic revisions. A PostgreSQL advisory lock allows only one to upgrade the schema; the other waits and then starts. Either service stops if migration fails.

3. Confirm the automatic migration completed:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml logs filament-manager worker
   ```

   The browser workbook import seeds the configured printer and initial physical P1-P5 plates with their Side A records automatically if they are missing. Administrators can also open **Printers** and choose **Seed configured printer** after signing in. To seed them separately from the browser, use the same idempotent service through the CLI:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml run --rm filament-manager filament-manager-cli seed-system
   ```

4. Verify all services:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml ps
   ```

5. Open `http://localhost:8080` and sign in with username `admin` and password `admin`. A new installation requires a password change before any other page is available. Then use **Settings** > **Workbook import** to upload the `.xlsx` master workbook. Validate the workbook, review any row findings, then commit the validated run only if this is a new empty inventory.

   The CLI remains available for headless recovery or automation. Bind-mount the workbook for the dry run, review every error and warning, then commit the exact unchanged file with the returned dry-run ID:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml run --rm -v "$(pwd)/reference:/import:ro" filament-manager filament-manager-cli workbook-dry-run "/import/Filament Inventory Master.xlsx"
   docker compose --env-file .env -f docker/docker-compose.yml run --rm -v "$(pwd)/reference:/import:ro" filament-manager filament-manager-cli workbook-commit --run-id DRY_RUN_UUID "/import/Filament Inventory Master.xlsx" --approved-by admin
   ```

Open `http://localhost:8080`. Spoolman remains independently available at `http://localhost:7912`.

The PostgreSQL initialization script runs only for a new empty volume. It never overwrites an existing database.

## Cura workstations

After the web application is available over HTTPS, install one outbound-only workstation agent under the normal Cura desktop account on every Arch Linux and Windows 11 computer. Pairing, user-service installation, Windows logon-task setup, discovery checks, and rollback are documented in [Cura Workstation Agent](docs/CURA_WORKSTATION_AGENT.md).

No workstation port or inbound firewall rule is required. Create the one-time enrollment code from **Cura workstations** in the web interface.

Before authoritative synchronization begins, review every reported material file and saved print profile on **Cura workstations**. For each source you want to preserve, choose the existing Filament Manager template it should update; leave every unwanted source as **Do not import**. Review all mappings, then use the single **Complete takeover** confirmation. See the workstation-agent guide for the bounded setting and expression-handling rules.

## Production Swarm with remote PostgreSQL

The root `docker-stack.yml` installs Spoolman, the Filament Manager web service, and the Filament Manager worker in one stack. It does not install PostgreSQL. The remote server remains authoritative and must be reachable from every Swarm node that may run these services.

### 1. Prepare the remote PostgreSQL server

Use PostgreSQL 17 where practical. Configure SCRAM password authentication, a firewall, and `pg_hba.conf` rules that permit only the Swarm node addresses. Filament Manager and Spoolman explicitly disable PostgreSQL TLS for this deployment, so credentials and database traffic are unencrypted and the database network must be dedicated, isolated, and inaccessible from untrusted systems. Do not expose PostgreSQL to the public internet.

After replacing `SWARM_NODE_CIDR` with the narrowest network that contains the approved Swarm nodes, the remote server needs rules equivalent to:

```text
host  filament_manager  filament_user  SWARM_NODE_CIDR  scram-sha-256
host  spoolman          spoolman_user  SWARM_NODE_CIDR  scram-sha-256
```

Keep broader application-role rules out of `pg_hba.conf`, set `password_encryption = 'scram-sha-256'`, and reload PostgreSQL after changing its listener, firewall, or access rules.

Create the private stack-variable file on the Swarm manager, then replace every example hostname, image owner, and credential. Generate a different hexadecimal password for each database role so the stack can safely assemble PostgreSQL URLs without percent-encoding:

```bash
cp .env.example .env
chmod 600 .env
openssl rand -hex 32
openssl rand -hex 32
```

Load the file before provisioning or command-line deployment. Docker Swarm does not load `.env` automatically:

```bash
set -a
. ./.env
set +a
export POSTGRES_ADMIN_USER=postgres
```

Run the repository provisioning SQL from a trusted host with `psql`. The command prompts for the PostgreSQL administrator password and sends the generated role passwords through standard input instead of command-line arguments:

```bash
{
  printf '\\set filament_manager_password %s\n' "$FILAMENT_MANAGER_DB_PASSWORD"
  printf '\\set spoolman_password %s\n' "$SPOOLMAN_DB_PASSWORD"
  cat docker/provision-databases.sql
} | psql --host "$POSTGRES_HOST" --port "$POSTGRES_PORT" --username "$POSTGRES_ADMIN_USER" --dbname postgres --password
```

This creates:

- database `filament_manager`, owned by `filament_user`;
- database `spoolman`, owned by `spoolman_user`;
- no cross-database grants.

The provisioning SQL is safe to rerun, but rerunning it rotates both role passwords to the supplied values. Update the matching stack variables in the same maintenance window.

Verify both least-privilege logins from an approved Swarm node before deploying. Explicitly disable TLS in both checks so the test matches the deployed clients:

```bash
PGPASSWORD="$FILAMENT_MANAGER_DB_PASSWORD" psql "host=$POSTGRES_HOST port=$POSTGRES_PORT dbname=$FILAMENT_MANAGER_DB_NAME user=$FILAMENT_MANAGER_DB_USERNAME sslmode=disable" -c 'SELECT current_database(), current_user;'
PGPASSWORD="$SPOOLMAN_DB_PASSWORD" psql "host=$POSTGRES_HOST port=$POSTGRES_PORT dbname=$SPOOLMAN_DB_NAME user=$SPOOLMAN_DB_USERNAME sslmode=disable" -c 'SELECT current_database(), current_user;'
```

### 2. Set stack variables

The Docker deployment is environment-only and does not mount an application configuration file. Set every deployment-specific value in `.env` or Portainer, including:

- `FILAMENT_MANAGER_BASE_URL` and exact optional `FILAMENT_MANAGER_ALLOWED_HOSTS`;
- remote PostgreSQL host, database names, roles, explicit non-SSL mode, and passwords;
- `SPOOLMAN_PUBLIC_URL` and the exact `SPOOLMAN_CORS_ORIGIN`;
- the one supported printer's `MOONRAKER_PRINTER_ID`, `MOONRAKER_PRINTER_NAME`, `MOONRAKER_BASE_URL`, and `MOONRAKER_NOZZLE_DIAMETER_MM`;
- optional Moonraker API key, Google publication values, and Bugsnag monitoring values;
- image tags, published ports, and any tuning values that differ from the documented defaults.

Leave `MOONRAKER_WEBSOCKET_URL` empty to derive `ws://.../websocket` or `wss://.../websocket` from `MOONRAKER_BASE_URL`. Pin Filament Manager to an immutable version tag or digest. `POSTGRES_HOST` must identify the remote server provisioned above. Keep `FILAMENT_MANAGER_DB_SSLMODE=disable` for psycopg and `SPOOLMAN_DB_QUERY=ssl=disable` for Spoolman's async PostgreSQL driver so neither application attempts TLS.

For initial testing, `ghcr.io/cosmicc/filament-manager:latest` tracks the newest CI-passing `main` build for AMD64 and ARM64. Before production use, replace it with the workflow's immutable `sha-<commit>` tag or resolved digest.

Keep `SPOOLMAN_RECONCILE_INTERVAL_MINUTES=1` so immediate event-driven projections have a frequent complete-rebuild safety net. `MOONRAKER_STATE_INTERVAL_SECONDS=10` aligns the active spool and build-plate side automatically while the printer is idle, `MOONRAKER_PRINT_INTERVAL_SECONDS=10` captures one combined live print/preflight snapshot, and `MOONRAKER_INFO_INTERVAL_SECONDS=300` refreshes sanitized printer details while idle. State, mesh, catalog, and information reads are deferred during an active print. `SYNC_OUTBOX_WORKERS=2` runs two fair dispatchers, and `SYNC_OUTBOX_LOCK_TIMEOUT_SECONDS=300` allows work abandoned by a terminated worker to be reclaimed without racing a normal bounded API request.

When Google publication is enabled, set `GOOGLE_ENABLED=true`, `GOOGLE_SPREADSHEET_ID`, and `GOOGLE_SERVICE_ACCOUNT_JSON`. The JSON must be compact and one line. When sourcing `.env` in a shell, surround the complete JSON value with single quotes.

Optional Bugsnag monitoring is disabled by default. To enable sanitized browser, FastAPI, and worker error reports, set:

```dotenv
BUGSNAG_ENABLED=true
BUGSNAG_API_KEY=<32-character SDK API key>
BUGSNAG_RELEASE_STAGE=production
BUGSNAG_BROWSER_PERFORMANCE_ENABLED=true
```

Leave browser performance disabled if only error reporting is wanted. The SDK API key is intentionally delivered to the browser when monitoring is enabled and therefore must not be treated as an account credential; never put a Bugsnag personal authentication token in this variable. Error reports use `notify.bugsnag.com`, and performance data uses the key-specific `<key>.otlp.bugsnag.com` host. Browser error-session reporting is disabled. Filament Manager continues operating if those outbound services are unavailable. Reports omit raw exception messages, private origins, queries, request bodies and headers, submitted values, users, sessions, hostnames, and credentials; frequent background-polling spans are discarded.

For readable production browser stack traces, add the separate Bugsnag Upload API key as the protected GitHub Actions repository secret `BUGSNAG_UPLOAD_API_KEY`. Direct pushes can then upload hidden source maps during the frontend build. Pull requests do not receive the secret or upload maps, and the runtime container never includes source-map files. The Upload API key is used only by CI; it is not delivered to the application or browser. Configure both the deployment SDK key and repository Upload API key when using browser monitoring from published images.

The current deployment intentionally uses ordinary environment variables instead of Docker secrets. Anyone with sufficient Portainer or Docker service-inspection access can read these values. Restrict that access, protect `.env` with mode `0600`, never commit it, and avoid printing `docker stack config` or service specifications into logs.

Browser sessions default to a fixed thirty-day lifetime and a rolling seven-day idle window. Keep `SESSION_LIFETIME_HOURS=720` and `SESSION_IDLE_MINUTES=10080` for that behavior; an actively used page refreshes its idle deadline without extending the fixed absolute expiry.

When converting an existing deployment, place the current database passwords, API key, and Google document into the matching variables before redeploying. Ensure the canonical database is owned by `filament_user` before changing `FILAMENT_MANAGER_DB_USERNAME`; do not silently point the application at an empty replacement database. Do not generate replacement database passwords unless the corresponding PostgreSQL roles are rotated in the same maintenance window. After all services are healthy on variables, obsolete Docker secret objects can be removed manually.

For migration and seed jobs, assemble the same canonical database URL used by the stack:

```bash
export FILAMENT_MANAGER_DATABASE_URL="postgresql+psycopg://${FILAMENT_MANAGER_DB_USERNAME}:${FILAMENT_MANAGER_DB_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${FILAMENT_MANAGER_DB_NAME}?sslmode=${FILAMENT_MANAGER_DB_SSLMODE}"
```

For Portainer Git-stack deployment, select the repository's root `docker-stack.yml` and enter the variables from `.env.example` in the stack environment-variable section. `POSTGRES_ADMIN_PASSWORD` is local-Compose-only. No account username or password variables are required, and no Docker config or Docker secret objects are used.

### 3. Deploy the stack and let it migrate automatically

Validate the fully interpolated stack and deploy it:

```bash
docker stack config -c docker-stack.yml > /dev/null
docker stack deploy --with-registry-auth -c docker-stack.yml filament-manager
docker stack services filament-manager
```

The web and worker entry points each check the canonical schema before starting. A stable PostgreSQL advisory lock serializes concurrent startup, so exactly one task applies pending Alembic revisions and the other continues afterward. Migration failure or a lock wait longer than `FILAMENT_MANAGER_DATABASE_MIGRATION_LOCK_TIMEOUT_SECONDS` stops that task. Confirm both services report `database_migration_completed` before normal startup:

```bash
docker service logs filament-manager_web
docker service logs filament-manager_worker
```

The 0.1.5 synchronization repair automatically requeues Spoolman jobs that previously became failed, dead, or stranded. Version 0.3.0 converts accumulated dead periodic jobs to retained `superseded` history, and later successful recurring runs automatically supersede older dead rows of the same type. Within one minute of the worker starting, it provisions the required Spoolman custom fields and projects every existing canonical vendor, filament, and spool. Confirm a `spoolman.reconcile.full` job completes in **Diagnostics**.

`FILAMENT_MANAGER_DATABASE_AUTO_MIGRATE` defaults to `true`. Disable it only for a controlled recovery. A separate migration job remains available for diagnosing a failed upgrade while the application services are stopped:

```bash
docker service create \
  --name filament-manager-migrate-recovery \
  --mode replicated-job \
  --no-healthcheck \
  --env "FILAMENT_MANAGER_DATABASE_URL=$FILAMENT_MANAGER_DATABASE_URL" \
  "$FILAMENT_MANAGER_IMAGE" \
  alembic upgrade head
docker service logs filament-manager-migrate-recovery
docker service rm filament-manager-migrate-recovery
```

The stack creates its `filament-services` overlay plus `filament_manager_data` and `spoolman_data` volumes. Canonical database backup ZIPs and restore-control files live under `/data/database-backups` in `filament_manager_data`. The image installs PostgreSQL client 18 for PostgreSQL 18 and older supported-server dumps. Backup creation waits for active prints to finish, and a failed automatic dump backs off from fifteen minutes to at most six hours rather than retrying every worker minute. On a multi-node Swarm, use shared storage or placement constraints so web, worker, and the zero-replica `database-restore` service always see that same volume data.

### Controlled database restore

Diagnostics can download existing snapshots or import a trusted Filament Manager backup ZIP. Selecting **Restore**, reviewing the archive, and typing `RESTORE` prepares the exact archive but does not modify a live database. For the root stack named `filament-manager`, complete the maintenance operation from a Swarm manager:

```bash
docker service scale filament-manager_web=0 filament-manager_worker=0
docker service scale filament-manager_database-restore=1
docker service logs --follow filament-manager_database-restore
docker service ps filament-manager_database-restore --no-trunc
docker service scale filament-manager_database-restore=0
docker service scale filament-manager_web=1 filament-manager_worker=1
```

Do not restart web or worker unless the restore task reports successful completion. The restore service creates a pre-restore safety ZIP, applies the selected dump in one transaction, upgrades older schemas forward, and revokes every restored browser session. If it fails, keep application services stopped and retain the pending request and safety archive for investigation. Use the actual stack name in place of `filament-manager` when different.

For local Compose, prepare the restore in Diagnostics and run:

```bash
docker compose stop filament-manager worker
docker compose --profile recovery run --rm database-restore
docker compose up -d filament-manager worker
```

The application backup feature intentionally covers only the canonical `filament_manager` database. Continue backing up the independently credentialed `spoolman` database through the PostgreSQL platform.

### 4. Seed the system and sign in

After the web and worker services are running, Administrators can open **Printers** and choose **Seed configured printer** to seed the configured printer and initial physical P1-P5 plates with Side A. Browser workbook import also seeds missing records automatically. If you need to perform setup without the browser, use a short-lived job:

```bash
docker service create \
  --name filament-manager-seed \
  --mode replicated-job \
  --no-healthcheck \
  --env "FILAMENT_MANAGER_DATABASE_URL=$FILAMENT_MANAGER_DATABASE_URL" \
  --env "FILAMENT_MANAGER_MOONRAKER_PRINTER_ID=$MOONRAKER_PRINTER_ID" \
  --env "FILAMENT_MANAGER_MOONRAKER_PRINTER_NAME=$MOONRAKER_PRINTER_NAME" \
  --env "FILAMENT_MANAGER_MOONRAKER_BASE_URL=$MOONRAKER_BASE_URL" \
  --env "FILAMENT_MANAGER_MOONRAKER_WEBSOCKET_URL=$MOONRAKER_WEBSOCKET_URL" \
  --env "FILAMENT_MANAGER_MOONRAKER_API_KEY=$MOONRAKER_API_KEY" \
  --env "FILAMENT_MANAGER_MOONRAKER_NOZZLE_DIAMETER_MM=$MOONRAKER_NOZZLE_DIAMETER_MM" \
  "$FILAMENT_MANAGER_IMAGE" \
  filament-manager-cli seed-system
docker service logs --follow filament-manager-seed
docker service rm filament-manager-seed
```

On an empty database, web startup creates the only local account as `admin` with password `admin`. Sign in and replace that password when prompted; all other routes remain blocked until the change succeeds. Username, display name, and password remain editable under **Settings → Account**. Existing one-account installations retain their current username and password during upgrade. A legacy database with more than one account must be reduced to the intended Administrator before upgrading because 0.3.0 fails startup instead of choosing or deleting an account. Version 0.3.0 intentionally does not accept Docker account-credential variables or provide account creation/reset endpoints.

### 5. Import the initial workbook on Swarm

The workbook importer is for an empty canonical spool inventory. It imports all populated rows from the `Inventory` sheet into canonical vendors, filament products, spools, measurements, and current material profiles where the required temperatures exist. Dashboard formulas, validation lists, the wishlist, and material-reference lookup data are supporting workbook content rather than canonical records and are not imported.

Copy the unchanged workbook onto one Swarm manager using a path without spaces. Keep it readable only by the operator, and run both jobs on that same node because a bind mount is node-local:

```bash
sudo install -d -m 0700 /opt/filament-manager/import
sudo install -m 0400 \
  "reference/Filament Inventory Master.xlsx" \
  /opt/filament-manager/import/filament-inventory.xlsx

docker service create \
  --name filament-manager-workbook-dry-run \
  --mode replicated-job \
  --constraint "node.hostname==$(hostname)" \
  --no-healthcheck \
  --env "FILAMENT_MANAGER_DATABASE_URL=$FILAMENT_MANAGER_DATABASE_URL" \
  --mount type=bind,src=/opt/filament-manager/import/filament-inventory.xlsx,dst=/import/filament-inventory.xlsx,readonly \
  "$FILAMENT_MANAGER_IMAGE" \
  filament-manager-cli workbook-dry-run /import/filament-inventory.xlsx
docker service logs --follow filament-manager-workbook-dry-run
```

Confirm that `invalid_rows` is `0`, then copy the returned `run_id`. Remove the completed validation job and commit the exact same hash-bound file using the existing Administrator username:

```bash
docker service rm filament-manager-workbook-dry-run

docker service create \
  --name filament-manager-workbook-commit \
  --mode replicated-job \
  --constraint "node.hostname==$(hostname)" \
  --no-healthcheck \
  --env "FILAMENT_MANAGER_DATABASE_URL=$FILAMENT_MANAGER_DATABASE_URL" \
  --mount type=bind,src=/opt/filament-manager/import/filament-inventory.xlsx,dst=/import/filament-inventory.xlsx,readonly \
  "$FILAMENT_MANAGER_IMAGE" \
  filament-manager-cli workbook-commit \
  --run-id DRY_RUN_UUID \
  /import/filament-inventory.xlsx \
  --approved-by ADMIN_USERNAME
docker service logs --follow filament-manager-workbook-commit
docker service rm filament-manager-workbook-commit
```

The commit is transactional and is refused if the workbook changed after validation, the approving account is not an Administrator, or any canonical spool already exists. After success, the worker projects the imported inventory to Spoolman through its supported API.

Open Filament Manager on the configured public URL and Spoolman on port `7912`. Verify `/health/ready`, `/metrics`, Spoolman's `/api/v1/health`, worker logs, and both remote PostgreSQL connections. The web probe uses the hostname from `FILAMENT_MANAGER_BASE_URL`; the stack disables this HTTP-only probe for the worker.

### Independent-stack alternative

The separate `docker/spoolman-stack.yml` and `docker/filament-manager-stack.yml` files remain available when Spoolman and Filament Manager must have independent deployment and rollback lifecycles. They use the same remote database provisioning and scoped stack variables described above. Set `SPOOLMAN_INTERNAL_URL=http://spoolman_spoolman:8000` for the default independent stack names. `FILAMENT_SERVICES_NETWORK`, `FILAMENT_MANAGER_DATA_VOLUME`, and `SPOOLMAN_DATA_VOLUME` select the pre-created external objects used by those files.

## Moonraker and Klipper

- Add `integrations/moonraker/moonraker-spoolman.conf` to Moonraker after replacing the LAN hostname.
- Before installing the app file, name the printer's existing physical load routine `[gcode_macro _FILAMENT_MANAGER_HARDWARE_LOAD]` and its existing physical unload routine `[gcode_macro _FILAMENT_MANAGER_HARDWARE_UNLOAD]`. Keep their movement bodies unchanged. Do not also define public `LOAD_FILAMENT` or `UNLOAD_FILAMENT` commands elsewhere.
- Copy `integrations/klipper/filament-manager-macros.cfg` to the Klipper configuration directory and include it **last**, after the files that define `START_PRINT`, `END_PRINT`, `CANCEL_PRINT`, `PURGE_FILAMENT`, and both reserved hardware routines. Replace the exact file named by the existing `[include ...]`; if that line still names `filament-manager_macros.cfg`, either overwrite that file or update the include instead of leaving the stale underscore-named copy active. Replace the installed copy on every Filament Manager upgrade; older copies can leave an `M25`-held Cura file at 0% after the purge line, fail to reset it when cancelled, or keep retrying a release condition indefinitely. Version 0.7.0 retries that release no more than every half second for thirty seconds before Fluidd shows explicit Retry and Cancel actions. Remove or disable any other `M600` definition. Filament Manager directly owns public `M600`, `LOAD_FILAMENT`, and `UNLOAD_FILAMENT`; only `CANCEL_PRINT` is preserved through `rename_existing`.
- If Klipper reports `Existing command 'LOAD_FILAMENT' not found in gcode_macro rename` or the equivalent `UNLOAD_FILAMENT` error, the installed app macro file is stale. Replace it with the current reference instead of creating a duplicate public command; the current file calls the two reserved hardware routines directly.
- Confirm `[respond]`, `[save_variables]`, `[pause_resume]`, and `[virtual_sdcard]` are configured. The supplied complete macro reference persists physical spool identity, the bounded material catalog, and the G-code inspection policy through `[save_variables]`.
- Before restarting, run `grep -Rns --include='*.cfg' 'variable_active_plate' ~/printer_data/config` on the Klipper host and confirm every included definition is exactly `variable_active_plate: "UNSET"`.
- Ensure Klipper already has P1, P2, P3, P4, and P5 Side A mesh profiles and a configured `[save_variables]` section before using `SELECT_BUILD_PLATE`.
- Restart Moonraker and issue `FIRMWARE_RESTART` in Klipper. Wait for the worker to initialize `FILAMENT_MANAGER_SPOOL_STATE`, then run that macro in the Fluidd console and confirm it reports `macro=0.7.0` plus the spool that is physically loaded, or no spool. If the version is absent or older, inspect the active `[include ...]` path before testing. Correct the existing Spoolman active ID before this first initialization if necessary.
- Run `LOAD_FILAMENT` with no ID and confirm Fluidd lists every projected, non-empty spool that has a safe temperature from its latest exact profile or linked printer/nozzle template. Publication is required for Cura print preflight, not for this manual-load chooser. If a spool is selected directly in Spoolman, wait for the next state pass and confirm the guarded target prompt opens before physical state changes.
- In Fluidd **Settings → Spoolman**, turn off **Show spool selection dialog on print start**. That independent selector activates its choice before a physical load and must not run alongside Filament Manager preflight. Do not use Fluidd's global **Change Spool** action to represent a future target; use the Filament Manager inventory **Load spool** action or the guarded macros instead.
- Allow the 0.7.0 workstation agent to install renderer revision 20 while Cura is closed, then start Cura once. For a selected managed product material, its saved machine start script supplies this boundary at slice time:

```gcode
FILAMENT_MANAGER_START_PRINT MATERIAL_GUID={material_guid, 0} BED_TEMP={material_bed_temperature_layer_0, 0} REGULAR_BED_TEMP={material_bed_temperature, 0} EXTRUDER_TEMP={material_print_temperature_layer_0, 0} CHAMBER_TEMP={build_volume_temperature}
```

  The workstation agent also saves `END_PRINT` as the matched printer's end G-code. It backs up and atomically overwrites both saved fields while Cura is closed, so no manual Cura script configuration is required.
- Save a product material profile and allow the workstation agent to synchronize Cura before printing. `Template <material type>` entries have no exact physical inventory mapping and are intentionally blocked by preflight.
- With the printer idle, verify `SELECT_BUILD_PLATE PLATE=P1`. Then request **Load spool** from Inventory and confirm Fluidd preheats and asks for the exact Spoolman ID. After the existing unload motion completes, Spoolman must show no active spool; only after insertion confirmation and the existing load motion completes may the new ID become active.
- Send a Cura test file with the already loaded matching product material and confirm it reaches the unchanged `START_PRINT` path without a load prompt, finishes the purge line, and immediately begins the sliced model. Repeat with another material and confirm Fluidd asks which exact matching spool to insert when more than one is available. If `START_PRINT` opens the app's build-plate chooser, select a side and confirm its deferred continuation finishes before the model begins.
- Keep **Settings → G-code inspection policy** at the recommended **Warn and continue** default for initial testing. Confirm Print History records matching metadata and any intentional test mismatch. Then, if desired, enable **Block mismatches** and verify Fluidd pauses at **Inspecting G-code**, releases a matching file, and retains a mismatched or unavailable file without running `START_PRINT`.
- Sign in, open **Build Plates**, and select the printer. Within 10 seconds while the printer is idle, exact `P<number>` meshes become Side A, exact `P<number>b` meshes become Side B of the same physical plate, and the loaded matching mesh becomes the active side.
- To add a physical plate later, save Side A as the next name, such as `P6`. If it is double-sided, save its other mesh as `P6b`. The next automatic state pass adds it; existing physical and side details are preserved, and missing meshes are shown as unavailable rather than deleted.

## Upgrade

1. Back up both databases independently.
2. Review release and migration notes.
3. Redeploy `docker-stack.yml` with the new pinned Filament Manager image; web and worker automatically serialize and apply the schema upgrade before starting.
4. Confirm both service logs report a completed migration and that no task is restarting.
5. Upgrade the Spoolman image separately in the same stack change, or leave its existing immutable tag unchanged.
6. Verify `/health/ready`, `/metrics`, job state, reconciliation, Moonraker, Cura synchronization, and Google publication.

See [Operations](docs/OPERATIONS.md) for backup, restore, and troubleshooting procedures.
See [Printing Workflow](docs/PRINTING_WORKFLOW.md) for the exact preflight, abort-state, history, assessment, and complete macro contract.
