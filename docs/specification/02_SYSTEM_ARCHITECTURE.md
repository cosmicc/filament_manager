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
|                                                                           |
|  stack: filament-manager                 stack: spoolman                   |
|  +-------------------------------+       +------------------------------+  |
|  | Filament Manager API + workers  |<----->| Spoolman API / WebSocket     |  |
|  +---------------+---------------+       +---------------+--------------+  |
|                  |                                       |                 |
|                  +---------- external overlay -----------+                 |
|                             filament-services                              |
+------------------|---------------------------------------|-----------------+
                   |                                       |
                   |                                       | published LAN endpoint
                   v                                       v
          central PostgreSQL server                 Klipper/Moonraker/Fluidd
          ├── filament_manager database                       printer host
          └── spoolman database
```

## Stack boundary

### Filament Manager stack

Contains only Filament Manager-owned services:

- API and web UI
- synchronization workers
- Google Sheet publisher
- Moonraker monitor
- future scale/NFC ingestion services

It does not contain Spoolman and does not control Spoolman's lifecycle.

### Spoolman stack

Contains the upstream Spoolman image as an independently deployed service. It owns:

- Spoolman process and migrations
- printer-facing API and WebSocket service
- Fluidd and Moonraker integration surface
- Spoolman-specific logs and operational state

## Central PostgreSQL server

Hosts two isolated databases:

- `filament_manager`: canonical records and audit history
- `spoolman`: Spoolman's internal database

Each database has its own owner and password. Filament Manager never queries or modifies Spoolman tables.

## Network model

### `filament-services`

An external attachable overlay network created before either stack is deployed. Both stacks join it. With the documented stack names, Filament Manager reaches Spoolman at:

```text
http://spoolman_spoolman:8000
```

The exact service DNS name is stack-name dependent and must remain configurable.

### Printer-facing endpoint

Moonraker runs outside Swarm and must use a stable LAN endpoint, for example:

```text
http://spoolman.internal.example:7912
```

Do not configure Moonraker with `spoolman_spoolman`; that name exists only inside the Swarm overlay.

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
