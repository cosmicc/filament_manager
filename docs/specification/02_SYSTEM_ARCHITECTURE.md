# 02 - System Architecture

## Production context

```text
                                    read-only publication
                              +-----------------------+
                              | Google Sheet          |
                              +-----------^-----------+
                                          |
                                          | one-way publisher
                                          |
+---------------- Docker Swarm ---------------------------------------------+
|  stack: filament-manager                                                   |
|  +-------------------------------+       +------------------------------+  |
|  | Filament Manager API + workers  |<----->| Spoolman API / WebSocket     |  |
|  +---------------+---------------+       +---------------+--------------+  |
|                  |                                       |                 |
|                  +----------- stack overlay ------------+                 |
|                             filament-services                              |
+------------------|---------------------------------------|-----------------+
                   |                                       |
                   |                                       | published LAN endpoint
                   v                                       v
          central PostgreSQL server                 Klipper/Moonraker/Fluidd
          ├── filament_manager database                       printer host
          └── spoolman database
```

## Service and deployment boundaries

### Filament Manager services

Contains only Filament Manager-owned services:

- API and web UI
- synchronization workers
- diagnostics aggregation, persisted recovery validation, and safe projection rebuild scheduling
- Google Sheet publisher
- Moonraker monitor
- future scale/NFC ingestion services

They do not receive Spoolman's database credential and do not control Spoolman's migrations.

### Spoolman service

Runs the upstream Spoolman image as a separately configurable service. It owns:

- Spoolman process and migrations
- printer-facing API and WebSocket service
- Fluidd and Moonraker integration surface
- Spoolman-specific logs and operational state

The root `docker-stack.yml` is the default deployment. The independent files under `docker/` preserve separate application stack boundaries for sites that need them.

Filament Manager's Docker services receive their complete validated runtime configuration from scoped environment variables. They do not mount an application config object. The current Docker contract configures one Moonraker printer.

The worker publishes a strict bounded Cura-material-to-Spoolman print catalog plus a separate bounded safe manual-load spool catalog through Moonraker and observes the persisted Klipper physical-spool macro every 15 seconds. Current exact profiles gate print preflight; a newest non-archived exact profile or linked in-scope template may supply a manual-load temperature. A direct non-null Spoolman selection becomes a guarded target only in safe selection phases and is restored to the persisted physical ID until confirmation. Klipper owns the unload/load commit boundary; requested future targets never become active canonical state before physical loading completes.

Physical nozzles are canonical installable inventory records. Print jobs capture the installed nozzle, exact plate side, and every spool segment so completed-use totals remain historical when hardware is later removed or retired. The Diagnostics API consolidates sanitized external, synchronization, worker-heartbeat, queue, and bounded error state; read-only validation results are persisted and rebuild requests only enqueue derived projections.

## Central PostgreSQL server

Hosts two isolated databases:

- `filament_manager`: canonical records and audit history
- `spoolman`: Spoolman's internal database

Each database has its own owner and password. Filament Manager never queries or modifies Spoolman tables.

## Network model

### `filament-services`

The combined stack creates this attachable overlay automatically. Filament Manager reaches Spoolman by its service name:

```text
http://spoolman:8000
```

The separate-stack deployment instead uses the stack-prefixed `http://spoolman_spoolman:8000` name on its pre-created external overlay.

### Printer-facing endpoint

Moonraker runs outside Swarm and must use a stable LAN endpoint, for example:

```text
http://spoolman.internal.example:7912
```

Do not configure Moonraker with `spoolman` or `spoolman_spoolman`; those names exist only inside a Swarm overlay.

### Reverse proxy

Spoolman and Filament Manager may independently join a reverse-proxy overlay. Authentication and exposure policy can differ by service.

## Component responsibilities

### Filament Manager API

Provides authenticated inventory, profile, plate, measurement, calibration, label, and operations endpoints.

### Filament Manager workers

- transactional outbox dispatcher
- Spoolman projector and reconciler
- Google Sheet publisher
- Moonraker connection monitor
- scheduled integrity checks
- future device telemetry processor

### Spoolman

Maintains printer-facing vendor, filament, spool, remaining-weight, and active-use state. Moonraker communicates with Spoolman through its supported integration.

### Google Sheet

Generated read model with suggested tabs:

- Dashboard
- Inventory
- Filament Profiles
- Build Plates
- Calibration Status
- Lists
- Activity Summary

### Hardware adapters

Future scale and NFC readers send authenticated events to Filament Manager. They do not connect directly to either PostgreSQL database.

## Data flows

### Inventory mutation

```text
User -> Filament Manager API -> canonical PostgreSQL transaction
                           -> outbox job
                           -> Spoolman API
                           -> Google publisher
```

### Print consumption

```text
Klipper/Moonraker -> Spoolman
                  -> Filament Manager API/WS reconciliation
                  -> canonical usage event
                  -> Google publication
```

### Manual weight correction

```text
User -> gross measurement -> remaining = gross - tare
     -> canonical correction event
     -> Spoolman API correction
     -> Google publication
```

## Availability model

- Spoolman remains available during Filament Manager deployment or failure.
- Filament Manager can be stopped without deliberately stopping Moonraker usage reporting.
- PostgreSQL is required for writes in each application, but database failures are isolated by database and role.
- Google failure queues publication work and never blocks printing.
- The Spoolman projection can be rebuilt from canonical Filament Manager records, then reconciled with printer-originated usage history.

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
