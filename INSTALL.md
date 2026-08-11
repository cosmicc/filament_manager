# Install Filament Manager

Use Docker Compose for a local workshop installation. The production `docker-stack.yml` deploys Filament Manager, its worker, and Spoolman together and assumes an existing remote PostgreSQL server.

## Local Docker Compose

Requirements: Docker Engine with Compose, `openssl`, and ports `8080` and `7912` available.

1. Create a private deployment-variable file from the template:

   ```bash
   cp .env.example .env
   chmod 600 .env
   openssl rand -hex 32       # Generate each database password separately.
   openssl rand -base64 36    # Generate the bootstrap Administrator password.
   ```

   Replace every `replace_with_...` value in `.env`. Use a different generated value for `POSTGRES_ADMIN_PASSWORD`, `FILAMENT_MANAGER_DB_PASSWORD`, and `SPOOLMAN_DB_PASSWORD`. For local HTTP access, set `FILAMENT_MANAGER_BASE_URL=http://localhost:8080`, `FILAMENT_MANAGER_ALLOWED_HOSTS=localhost,127.0.0.1`, `FILAMENT_MANAGER_SECURE_COOKIES=false`, and `SPOOLMAN_PUBLIC_URL=http://localhost:7912`. Set the one printer's Moonraker ID, name, URL, and nozzle diameter, plus the initial Administrator username and display name. The ignored `.env` file contains credentials; never commit it.

2. Build and start PostgreSQL and the distinct Spoolman service:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml build
   docker compose --env-file .env -f docker/docker-compose.yml up -d postgres spoolman
   ```

3. Apply the canonical schema and seed the configured printer plus P1–P5:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml run --rm filament-manager alembic upgrade head
   docker compose --env-file .env -f docker/docker-compose.yml run --rm filament-manager filament-manager-cli seed-system
   ```

4. Create the first local Administrator. No default account is created:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml run --rm bootstrap-admin
   ```

5. Validate and import the supplied workbook only if this is a new empty inventory:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml run --rm -v "$(pwd)/reference:/import:ro" filament-manager filament-manager-cli workbook-dry-run "/import/Filament Inventory Master.xlsx"
   ```

   The production image does not include the reference workbook by default. Bind-mount it for that one command or run the CLI from the checked-out repository. Review every error and warning, then commit the exact unchanged file with the returned dry-run ID:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml run --rm -v "$(pwd)/reference:/import:ro" filament-manager filament-manager-cli workbook-commit --run-id DRY_RUN_UUID "/import/Filament Inventory Master.xlsx" --approved-by admin
   ```

6. Start the web application and worker:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml up -d filament-manager worker
   ```

Open `http://localhost:8080`. Spoolman remains independently available at `http://localhost:7912`.

The PostgreSQL initialization script runs only for a new empty volume. It never overwrites an existing database.

## Cura workstations

After the web application is available over HTTPS, install one outbound-only workstation agent under the normal Cura desktop account on every Arch Linux and Windows 11 computer. Pairing, user-service installation, Windows logon-task setup, discovery checks, and rollback are documented in [Cura Workstation Agent](docs/CURA_WORKSTATION_AGENT.md).

No workstation port or inbound firewall rule is required. Create the one-time enrollment code from **Cura workstations** in the web interface.

## Production Swarm with remote PostgreSQL

The root `docker-stack.yml` installs Spoolman, the Filament Manager web service, and the Filament Manager worker in one stack. It does not install PostgreSQL. The remote server remains authoritative and must be reachable from every Swarm node that may run these services.

### 1. Prepare the remote PostgreSQL server

Use PostgreSQL 17 where practical. Configure TLS, SCRAM password authentication, a firewall, and `pg_hba.conf` rules that permit only the Swarm node addresses. Do not expose PostgreSQL to the public internet.

After replacing `SWARM_NODE_CIDR` with the narrowest network that contains the approved Swarm nodes, the remote server needs rules equivalent to:

```text
hostssl  filament_manager  filament_manager_user  SWARM_NODE_CIDR  scram-sha-256
hostssl  spoolman          spoolman_user           SWARM_NODE_CIDR  scram-sha-256
```

Keep broader application-role rules out of `pg_hba.conf`, set `password_encryption = 'scram-sha-256'`, and reload PostgreSQL after changing its listener, TLS, firewall, or access rules.

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

- database `filament_manager`, owned by `filament_manager_user`;
- database `spoolman`, owned by `spoolman_user`;
- no cross-database grants.

The provisioning SQL is safe to rerun, but rerunning it rotates both role passwords to the supplied values. Update the matching stack variables in the same maintenance window.

Verify both least-privilege logins from an approved Swarm node before deploying. Use TLS parameters that match the remote server's certificate policy:

```bash
PGPASSWORD="$FILAMENT_MANAGER_DB_PASSWORD" psql "host=$POSTGRES_HOST port=$POSTGRES_PORT dbname=$FILAMENT_MANAGER_DB_NAME user=$FILAMENT_MANAGER_DB_USERNAME sslmode=$FILAMENT_MANAGER_DB_SSLMODE" -c 'SELECT current_database(), current_user;'
PGPASSWORD="$SPOOLMAN_DB_PASSWORD" psql "host=$POSTGRES_HOST port=$POSTGRES_PORT dbname=$SPOOLMAN_DB_NAME user=$SPOOLMAN_DB_USERNAME sslmode=require" -c 'SELECT current_database(), current_user;'
```

Prefer `sslmode=verify-full` when the remote server certificate chains to a CA trusted by the application images.

### 2. Set stack variables

The Docker deployment is environment-only and does not mount an application configuration file. Set every deployment-specific value in `.env` or Portainer, including:

- `FILAMENT_MANAGER_BASE_URL` and exact optional `FILAMENT_MANAGER_ALLOWED_HOSTS`;
- remote PostgreSQL host, database names, roles, TLS mode, and passwords;
- `SPOOLMAN_PUBLIC_URL` and the exact `SPOOLMAN_CORS_ORIGIN`;
- the one supported printer's `MOONRAKER_PRINTER_ID`, `MOONRAKER_PRINTER_NAME`, `MOONRAKER_BASE_URL`, and `MOONRAKER_NOZZLE_DIAMETER_MM`;
- optional Moonraker API key and Google publication values;
- image tags, published ports, and any tuning values that differ from the documented defaults.

Leave `MOONRAKER_WEBSOCKET_URL` empty to derive `ws://.../websocket` or `wss://.../websocket` from `MOONRAKER_BASE_URL`. Pin Filament Manager to an immutable version tag or digest. `POSTGRES_HOST` must identify the remote server provisioned above. `SPOOLMAN_DB_QUERY=ssl=require` uses Spoolman's async PostgreSQL driver to require encryption; use the server's stronger verified TLS settings when supported by its certificate deployment.

For initial testing, `ghcr.io/cosmicc/filament-manager:latest` tracks the newest CI-passing `main` build for AMD64 and ARM64. Before production use, replace it with the workflow's immutable `sha-<commit>` tag or resolved digest.

When Google publication is enabled, set `GOOGLE_ENABLED=true`, `GOOGLE_SPREADSHEET_ID`, and `GOOGLE_SERVICE_ACCOUNT_JSON`. The JSON must be compact and one line. When sourcing `.env` in a shell, surround the complete JSON value with single quotes.

The current deployment intentionally uses ordinary environment variables instead of Docker secrets. Anyone with sufficient Portainer or Docker service-inspection access can read these values. Restrict that access, protect `.env` with mode `0600`, never commit it, and avoid printing `docker stack config` or service specifications into logs.

When converting an existing deployment, place the current database passwords, API key, and Google document into the matching variables before redeploying. Do not generate replacement database passwords unless the corresponding PostgreSQL roles are rotated in the same maintenance window. After all services are healthy on variables, obsolete Docker secret objects can be removed manually.

For the migration, seed, and bootstrap jobs, assemble the same canonical database URL used by the stack:

```bash
export FILAMENT_MANAGER_DATABASE_URL="postgresql+psycopg://${FILAMENT_MANAGER_DB_USERNAME}:${FILAMENT_MANAGER_DB_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${FILAMENT_MANAGER_DB_NAME}?sslmode=${FILAMENT_MANAGER_DB_SSLMODE}"
```

For Portainer Git-stack deployment, select the repository's root `docker-stack.yml` and enter the variables from `.env.example` in the stack environment-variable section. `POSTGRES_ADMIN_PASSWORD` is local-Compose-only, and the bootstrap variables belong only on the one-shot bootstrap job. No Docker config or Docker secret objects are required.

### 3. Run the migration and deploy the stack

Run migrations as a separate one-shot job before the application services. The migration receives only the Filament Manager database URL variable:

```bash
docker service create \
  --name filament-manager-migrate-v0-1-0 \
  --mode replicated-job \
  --env "FILAMENT_MANAGER_DATABASE_URL=$FILAMENT_MANAGER_DATABASE_URL" \
  "$FILAMENT_MANAGER_IMAGE" \
  alembic upgrade head
```

Confirm the job completed successfully, inspect its logs, and then remove the completed job:

```bash
docker service ps filament-manager-migrate-v0-1-0 --no-trunc
docker service logs filament-manager-migrate-v0-1-0
docker service rm filament-manager-migrate-v0-1-0
```

Validate the fully interpolated stack and deploy it:

```bash
docker stack config -c docker-stack.yml > /dev/null
docker stack deploy --with-registry-auth -c docker-stack.yml filament-manager
docker stack services filament-manager
```

The stack creates its `filament-services` overlay plus `filament_manager_data` and `spoolman_data` volumes. On a multi-node Swarm, use shared storage or placement constraints so stateful volume paths cannot move to an empty node.

### 4. Seed the system and create the first Administrator

After the web and worker services are running, use a short-lived job to seed the configured printer and P1-P5:

```bash
docker service create \
  --name filament-manager-seed \
  --mode replicated-job \
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

Create the first Administrator with the bootstrap password variable scoped only to a short-lived job. Replace the example username and display name before running the job:

```bash
docker service create \
  --name filament-manager-bootstrap-admin \
  --mode replicated-job \
  --env "FILAMENT_MANAGER_DATABASE_URL=$FILAMENT_MANAGER_DATABASE_URL" \
  --env "FILAMENT_MANAGER_BOOTSTRAP_ADMIN_PASSWORD=$BOOTSTRAP_ADMIN_PASSWORD" \
  "$FILAMENT_MANAGER_IMAGE" \
  filament-manager-cli bootstrap-admin \
  --username "$BOOTSTRAP_ADMIN_USERNAME" \
  --display-name "$BOOTSTRAP_ADMIN_DISPLAY_NAME"
docker service logs --follow filament-manager-bootstrap-admin
docker service rm filament-manager-bootstrap-admin
unset BOOTSTRAP_ADMIN_PASSWORD
```

No default account is created. The bootstrap job refuses to run after any user already exists. Clear `BOOTSTRAP_ADMIN_PASSWORD` from `.env` and Portainer after success; the long-running web and worker services never receive it.

Open Filament Manager on the configured public URL and Spoolman on port `7912`. Verify `/health/ready`, `/metrics`, Spoolman's `/api/v1/health`, worker logs, and both remote PostgreSQL connections.

### Independent-stack alternative

The separate `docker/spoolman-stack.yml` and `docker/filament-manager-stack.yml` files remain available when Spoolman and Filament Manager must have independent deployment and rollback lifecycles. They use the same remote database provisioning and scoped stack variables described above. Set `SPOOLMAN_INTERNAL_URL=http://spoolman_spoolman:8000` for the default independent stack names. `FILAMENT_SERVICES_NETWORK`, `FILAMENT_MANAGER_DATA_VOLUME`, and `SPOOLMAN_DATA_VOLUME` select the pre-created external objects used by those files.

## Moonraker and Klipper

- Add `integrations/moonraker/moonraker-spoolman.conf` to Moonraker after replacing the LAN hostname.
- Include `integrations/klipper/filament-manager-macros.cfg` from `printer.cfg`.
- Ensure Klipper already has P1, P2, P3, P4, and P5 mesh profiles and a configured `[save_variables]` section before using `SELECT_BUILD_PLATE`.
- Restart Moonraker and Klipper, then test `SET_ACTIVE_SPOOL ID=<Spoolman ID>` and `SELECT_BUILD_PLATE PLATE=P1` with the printer idle.

## Upgrade

1. Back up both databases independently.
2. Review release and migration notes.
3. Run the new Filament Manager migration job.
4. Redeploy `docker-stack.yml` with the new pinned Filament Manager image.
5. Upgrade the Spoolman image separately in the same stack change, or leave its existing immutable tag unchanged.
6. Verify `/health/ready`, `/metrics`, job state, reconciliation, Moonraker, and Google publication.

See [Operations](docs/OPERATIONS.md) for backup, restore, and troubleshooting procedures.
