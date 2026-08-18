# 07 - Standalone Spoolman Integration

## Production decision

Spoolman is a distinct service with its own image, remote database, credential, migrations, volume, health check, and update policy. The default `docker-stack.yml` deploys it beside Filament Manager; optional independent stack files preserve a stronger rollout boundary. Spoolman provides the established spool API, WebSocket events, labels and QR workflow, Moonraker integration, and Fluidd user experience.

## Rationale

- an independently pinned image and stop-first updates
- failure isolation from Filament Manager development
- continuous Moonraker usage reporting during Filament Manager restarts
- reuse by additional printers
- clear ownership of Spoolman migrations and runtime configuration

## Database

Spoolman uses its own `spoolman` PostgreSQL database and `spoolman_user` role on the central server. The password is currently passed through `SPOOLMAN_DB_PASSWORD` only to the Spoolman service.

Filament Manager must never write directly to Spoolman tables. All reads and writes use the REST API or WebSocket interfaces.

## Ports and addresses

- Spoolman container port: TCP `8000`
- recommended published LAN port: TCP `7912`
- Filament Manager combined-stack URL: `http://spoolman:8000`
- Filament Manager separate-stack URL: `http://spoolman_spoolman:8000`
- Moonraker URL: stable LAN DNS or IP, such as `http://spoolman.internal.example:7912`

The Swarm-internal service DNS name is not usable from the printer host.

## Shared overlay network

The root stack creates its attachable `filament-services` overlay automatically. The optional independent stack deployment uses a pre-created external overlay with the same name.

## Required environment variables

```yaml
environment:
  TZ: America/Detroit
  SPOOLMAN_HOST: 0.0.0.0
  SPOOLMAN_PORT: "8000"
  SPOOLMAN_DB_TYPE: postgres
  SPOOLMAN_DB_HOST: postgres.internal.example
  SPOOLMAN_DB_PORT: "5432"
  SPOOLMAN_DB_NAME: spoolman
  SPOOLMAN_DB_USERNAME: spoolman_user
  SPOOLMAN_DB_PASSWORD: ${SPOOLMAN_DB_PASSWORD}
```

Optional browser and security controls:

```yaml
  SPOOLMAN_CORS_ORIGIN: https://fluidd.internal.example
```

`SPOOLMAN_CORS_ORIGIN` is for browser origins such as Fluidd hosted elsewhere. It is not required for Moonraker. Spoolman 0.23.1 does not provide an allowed-host or authentication setting, so restrict its published port with the firewall or an authenticated reverse proxy.

## Persistent directory

Mount `/home/app/.local/share/spoolman` even when PostgreSQL stores inventory. It retains logs and other application-local runtime files. The combined stack creates the volume; on a multi-node Swarm, back it with shared storage or constrain Spoolman to the node that owns it.

## Service policy

- one replica
- pin a tested image tag; do not use `latest` in production
- `stop-first` updates to avoid concurrent database migrations
- rollback on failed update
- API health check at `/api/v1/health`
- independent log collection and Prometheus scraping

## Object mapping

### Vendor

Manufacturer name and selected custom metadata.

### Filament

Material, vendor, product name/grade/hardness, diameter, density, nominal weight, primary color, Filament Manager display palette, temperatures, and compatible custom fields.

### Spool

Physical spool, initial weight, tare weight, remaining and used weight, price, first/last use, location, comment, and managed identifiers.

The Spoolman active ID is an operational observation of what is physically loaded, never a reservation for the next spool. Klipper clears it only after the physical unload routine completes and sets the exact replacement only after the physical load routine completes. Filament Manager Inventory and public macros request that workflow instead of pre-activating a target. The worker repairs accidental direct Fluidd/Moonraker changes to the persisted physical macro value.

Canonical creates and edits enqueue an immediate transactional outbox projection. A complete convergence sweep runs every minute by default. It reads printer-originated remaining weight before metadata projection, then upserts every canonical vendor, filament, and spool. Routine metadata updates omit `remaining_weight`; only initial creation and explicit measurement jobs write it.

## Required custom fields

The worker idempotently provisions these text fields through `POST /api/v1/field/{entity_type}/{key}` before projecting records:

- vendor: `filament_manager_vendor_uuid`
- filament: `filament_manager_product_uuid`, `filler`, `finish`, `color_name`, and `display_palette`
- spool: `filament_manager_spool_uuid` and `sheet_spool_id`

Spoolman stores every custom-field value as a JSON-encoded string. Encode managed values before create/update and decode them before UUID comparison. Managed UUID discovery makes retries duplicate-safe when a worker stops after remote creation but before saving the local remote ID.

## Extra-field safety

Spoolman API updates can replace an object's `extra` mapping. Read the current object, merge unknown keys, and send the merged result. Do not erase fields owned by another integration. Paginate vendor, filament, and spool collections with `limit`, `offset`, and `x-total-count`; reconciliation must never silently stop at one API page.

## Deployment example

Use the repository root `docker-stack.yml` for the default combined deployment. Use `docker/spoolman-stack.yml` only when the independent-stack lifecycle is required. Verify the API from both a Swarm node and the printer network.

## Authoritative implementation references

- Spoolman repository: https://github.com/Donkie/Spoolman
- Spoolman Docker installation: https://github.com/Donkie/Spoolman/wiki/Installation
- Spoolman configuration variables: https://github.com/Donkie/Spoolman/blob/master/.env.example
- Spoolman security guidance: https://github.com/Donkie/Spoolman/wiki/Security
- Spoolman REST API: https://donkie.github.io/Spoolman/
- Moonraker Spoolman configuration: https://moonraker.readthedocs.io/en/stable/configuration/#spoolman
- Fluidd Spoolman support: https://docs.fluidd.xyz/features/spoolman
- Google Sheets API: https://developers.google.com/workspace/sheets/api
- Docker Swarm stack deployment: https://docs.docker.com/engine/swarm/stack-deploy/
- PostgreSQL documentation: https://www.postgresql.org/docs/
