# Architecture

## Authority model

Filament Manager uses PostgreSQL as the only canonical business database. The supplied workbook is a hash-bound initial import source, not an ongoing database. Google Sheets is a one-way protected publication. Standalone Spoolman is the printer-facing operational projection and usage source; Filament Manager never reads or writes Spoolman tables.

```text
Browser -> FastAPI -> filament_manager PostgreSQL
                    -> transactional outbox -> worker -> Spoolman REST API
                                                  |----> Moonraker HTTP API
                                                  `----> Google Sheets API

Cura workstation agent -> outbound HTTPS polling -> FastAPI -> leased desired library
                     `-> local backup -> atomic material/plugin replacement

Moonraker/Fluidd -> Spoolman service -> periodic supported-API reconciliation
```

The default production deployment operates Spoolman and Filament Manager as separate services in one Swarm stack. The stack creates a private `filament-services` overlay, while Moonraker uses Spoolman's stable published LAN address. Separate application stack files remain available when independent deployment lifecycles are required. Both layouts use remote PostgreSQL with isolated databases and roles.

Docker services build their validated runtime configuration directly from stack environment variables. No application configuration file is mounted. The current Docker contract accepts one Moonraker printer and derives its WebSocket endpoint from its HTTP base URL unless an explicit override is supplied.

## Canonical domains

- local Users, revocable sessions, and Administrator/Operator/Viewer roles
- Vendors, Filament Products, uniquely labeled Spools, and immutable physical Measurements
- immutable Spool Usage Events imported from supported Spoolman state
- Printers, physical Build Plates, and printable sides; `P4` is Side A and `P4b` is Side B of physical plate P4
- versioned Material Profiles and resumable six-step Calibration Sessions
- append-only Audit Events, transactional Outbox Jobs, and Projection State
- revisioned generic Material Templates, product-owned Material Profiles, revocable Workstation Agents, single-use Pairing Codes, and immutable desired-library Deployment snapshots
- future authenticated Device adapters and identifier-only NFC mappings

Mass, density, dimensions, calibration factors, and money use PostgreSQL `NUMERIC`. Technical identities use UUIDs. Mutable rows use optimistic integer record versions. Times are stored in UTC and presented in America/Detroit.

## Mutation and synchronization rules

A canonical change, its audit record, and all required projection jobs commit in one transaction. Workers claim jobs with `FOR UPDATE SKIP LOCKED`, retry with bounded exponential backoff, and never expose payloads or secrets in logs. PostgreSQL transaction advisory locks coordinate periodic scheduling across workers.

Physical measurements have higher confidence than usage estimates. A measurement stores gross, the exact tare used, net, expected-before, variance, confirmation, source, operator, and time. Unknown imported tare is established atomically with the first verified measurement. Historical usage is never rewritten.

Spoolman reconciliation accepts only supported API data. Decreases create immutable usage events and update effective expected mass; identity-sensitive remote changes remain canonical in Filament Manager. A legacy spool whose location ownership has never been established may adopt one existing, bounded Spoolman location. After import or any local edit, Filament Manager owns that free-text bucket value and reconciliation repairs remote drift. Projection updates read and merge Spoolman `extra` fields so another integration's keys are preserved.

Administrator-triggered build-plate synchronization reads Moonraker's supported `bed_mesh` printer object before opening its short canonical transaction. Exact bounded `P<number>` and `P<number>b` profiles create physical plates and sides, missing meshes update side availability without deleting metadata, and a loaded matching mesh updates the printer's active physical plate and side. All other profile names are ignored.

## Security boundaries

- Local passwords use Argon2id; no default user exists.
- Browser sessions are random, hashed server-side, revocable, HttpOnly, SameSite Strict, CSRF-bound, and time-limited.
- Role checks are server-side on every route.
- Configuration rejects credentials embedded in integration URLs.
- Database URLs, API keys, and service-account documents currently enter Docker services through scoped environment variables. Values remain masked in application models and must never be logged; populated `.env` files and Docker/Portainer operator access are tightly restricted.
- PostgreSQL connections explicitly disable TLS on the dedicated isolated database network. This exposes credentials and queries to network observers and must never be extended onto a shared or untrusted network.
- Trusted hosts, exact CORS origins, security headers, sanitized API errors, login throttling, and least-privilege containers are enabled.
- Spoolman has no built-in authentication; keep its LAN endpoint firewalled and put remote browser access behind an authenticated proxy.
- Workstation agents have no listener. Pairing codes expire after ten minutes and are consumed once; long-lived agent credentials are stored as hashes and authorize only agent heartbeat, claim, and completion routes.
- Cura writes occur only while Cura is closed, under verified discovered data roots, with symlink/root-escape rejection, automatic backups, full-library checksums, atomic desired-state material/plugin replacement, and rollback. Existing-material discovery uses hardened XML parsing, approved keys, bounded payloads, and no local paths. Authoritative takeover is automatic only for a clean user material directory and otherwise requires Administrator confirmation.
- Docker web and worker startup coordinate Alembic upgrades with one bounded PostgreSQL session advisory lock before either long-running process starts.

## Repository map

- `src/filament_manager/`: API, domain policy, models, clients, import, and workers
- `migrations/`: reversible Alembic schema history
- `frontend/`: React/TypeScript application and Playwright checks
- `workstation-agent/`: Arch Linux and Windows 11 Cura discovery, installers, deployment writer, and agent tests
- `docker-stack.yml`: combined production Swarm deployment using remote PostgreSQL
- `docker/`: environment-only local Compose, optional independent production stacks, and remote database provisioning
- `integrations/`: Moonraker and Klipper examples
- `docs/specification/`: complete imported source documentation
- `mappings/`, `schemas/`, `reference/`: import contracts and original workbook fixture
- `skills/`: focused agent procedures indexed by `AGENTS.md`
