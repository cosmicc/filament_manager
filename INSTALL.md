# Install Filament Manager

Use Docker Compose for a local workshop installation. Production uses the two independent Swarm stacks under `docker/` and an existing central PostgreSQL server.

## Local Docker Compose

Requirements: Docker Engine with Compose, `openssl`, and ports `8080` and `7912` available.

1. Create local secret files with restrictive permissions:

   ```bash
   mkdir -p secrets
   chmod 700 secrets
   openssl rand -hex 32 > secrets/postgres-admin-password.txt
   openssl rand -hex 32 > secrets/filament-manager-db-password.txt
   openssl rand -hex 32 > secrets/spoolman-db-password.txt
   openssl rand -base64 36 > secrets/bootstrap-admin-password.txt
   chmod 600 secrets/*.txt
   ```

2. Create `secrets/filament-manager-database-url.txt`. Its password must exactly match `filament-manager-db-password.txt`, not the PostgreSQL administrator secret:

   ```text
   postgresql+psycopg://filament_manager_user:REPLACE_WITH_POSTGRES_PASSWORD@postgres:5432/filament_manager
   ```

3. Review `config/config.local.docker.yaml`, especially the printer name, nozzle, and Moonraker address.

4. Build and start PostgreSQL and standalone Spoolman:

   ```bash
   docker compose -f docker/docker-compose.yml build
   docker compose -f docker/docker-compose.yml up -d postgres spoolman
   ```

5. Apply the canonical schema and seed the configured printer plus P1–P5:

   ```bash
   docker compose -f docker/docker-compose.yml run --rm filament-manager alembic upgrade head
   docker compose -f docker/docker-compose.yml run --rm filament-manager filament-manager-cli seed-system
   ```

6. Create the first local Administrator. No default account is created:

   ```bash
   docker compose -f docker/docker-compose.yml run --rm bootstrap-admin
   ```

7. Validate and import the supplied workbook only if this is a new empty inventory:

   ```bash
   docker compose -f docker/docker-compose.yml run --rm -v "$(pwd)/reference:/import:ro" filament-manager filament-manager-cli workbook-dry-run "/import/Filament Inventory Master.xlsx"
   ```

   The production image does not include the reference workbook by default. Bind-mount it for that one command or run the CLI from the checked-out repository. Review every error and warning, then commit the exact unchanged file with the returned dry-run ID:

   ```bash
   docker compose -f docker/docker-compose.yml run --rm -v "$(pwd)/reference:/import:ro" filament-manager filament-manager-cli workbook-commit --run-id DRY_RUN_UUID "/import/Filament Inventory Master.xlsx" --approved-by admin
   ```

8. Start the web application and worker:

   ```bash
   docker compose -f docker/docker-compose.yml up -d filament-manager worker
   ```

Open `http://localhost:8080`. Spoolman remains independently available at `http://localhost:7912`.

The PostgreSQL initialization script runs only for a new empty volume. It never overwrites an existing database.

## Cura workstations

After the web application is available over HTTPS, install one outbound-only workstation agent under the normal Cura desktop account on every Arch Linux and Windows 11 computer. Pairing, user-service installation, Windows logon-task setup, discovery checks, and rollback are documented in [Cura Workstation Agent](docs/CURA_WORKSTATION_AGENT.md).

No workstation port or inbound firewall rule is required. Create the one-time enrollment code from **Cura workstations** in the web interface.

## Production Swarm

Production keeps the `filament_manager` and `spoolman` databases and roles separate on the central PostgreSQL server. Run `docker/provision-databases.sql` as a database administrator and pass both generated passwords as `psql` variables; never edit passwords into the SQL file.

Create the shared network, external volumes, secrets, and versioned config:

```bash
docker network create --driver overlay --attachable filament-services
docker volume create spoolman_data
docker volume create filament_manager_data
docker secret create spoolman_db_password secrets/spoolman-db-password.txt
docker secret create filament_manager_database_url secrets/filament-manager-database-url.txt
docker secret create moonraker_api_key secrets/moonraker-api-key.txt
docker secret create google_service_account secrets/google-service-account.json
docker config create filament_manager_config_v1 config/config.yaml
```

Set `.env` from `.env.example`, replace every example hostname and image owner, and pin immutable image tags or digests. Deploy Spoolman first:

```bash
docker stack deploy -c docker/spoolman-stack.yml spoolman
```

Run migrations as a one-shot Swarm job before each Filament Manager rollout:

```bash
docker service create --name filament-manager-migrate-v0-1-0 --mode replicated-job --network filament-services --env FILAMENT_MANAGER_CONFIG=/config/config.yaml --config source=filament_manager_config_v1,target=/config/config.yaml --secret filament_manager_database_url "${FILAMENT_MANAGER_IMAGE}" alembic upgrade head
```

After the migration job completes successfully, deploy the application:

```bash
docker stack deploy -c docker/filament-manager-stack.yml filament-manager
```

Create the first Administrator with a separate short-lived Swarm secret and remove that bootstrap service and secret after success. Never mount the Spoolman database password into Filament Manager.

## Moonraker and Klipper

- Add `integrations/moonraker/moonraker-spoolman.conf` to Moonraker after replacing the LAN hostname.
- Include `integrations/klipper/filament-manager-macros.cfg` from `printer.cfg`.
- Ensure Klipper already has P1, P2, P3, P4, and P5 mesh profiles and a configured `[save_variables]` section before using `SELECT_BUILD_PLATE`.
- Restart Moonraker and Klipper, then test `SET_ACTIVE_SPOOL ID=<Spoolman ID>` and `SELECT_BUILD_PLATE PLATE=P1` with the printer idle.

## Upgrade

1. Back up both databases independently.
2. Review release and migration notes.
3. Run the new Filament Manager migration job.
4. Redeploy only `filament-manager-stack.yml`.
5. Upgrade Spoolman separately with `spoolman-stack.yml`.
6. Verify `/health/ready`, `/metrics`, job state, reconciliation, Moonraker, and Google publication.

See [Operations](docs/OPERATIONS.md) for backup, restore, and troubleshooting procedures.
