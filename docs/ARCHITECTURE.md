# Architecture

## Authority model

Filament Manager uses PostgreSQL as the only canonical business database. The supplied workbook is a hash-bound initial import source, not an ongoing database. Google Sheets is a one-way protected publication. Standalone Spoolman is the printer-facing operational projection and usage source; Filament Manager never reads or writes Spoolman tables.

```text
Browser -> FastAPI -> filament_manager PostgreSQL
                    -> transactional outbox -> worker -> Spoolman REST API
                                                  |----> Moonraker HTTP API
                                                  `----> Google Sheets API

Cura workstation agent -> outbound HTTPS polling -> FastAPI -> leased profile snapshot
                     `-> local backup -> atomic Cura material/quality/start-G-code update

Moonraker/Fluidd -> standalone Spoolman -> periodic supported-API reconciliation
```

Production operates Spoolman and Filament Manager as separate Swarm stacks. Both join the external `filament-services` overlay, while Moonraker uses Spoolman's stable LAN address.

## Canonical domains

- local Users, revocable sessions, and Administrator/Operator/Viewer roles
- Vendors, Filament Products, uniquely labeled Spools, and immutable physical Measurements
- immutable Spool Usage Events imported from supported Spoolman state
- Printers and physical Build Plates P1–P5 mapped to same-named Klipper mesh profiles
- versioned Material Profiles and resumable six-step Calibration Sessions
- append-only Audit Events, transactional Outbox Jobs, and Projection State
- revocable Workstation Agents, single-use Pairing Codes, and immutable Cura Deployment snapshots
- future authenticated Device adapters and identifier-only NFC mappings

Mass, density, dimensions, calibration factors, and money use PostgreSQL `NUMERIC`. Technical identities use UUIDs. Mutable rows use optimistic integer record versions. Times are stored in UTC and presented in America/Detroit.

## Mutation and synchronization rules

A canonical change, its audit record, and all required projection jobs commit in one transaction. Workers claim jobs with `FOR UPDATE SKIP LOCKED`, retry with bounded exponential backoff, and never expose payloads or secrets in logs. PostgreSQL transaction advisory locks coordinate periodic scheduling across workers.

Physical measurements have higher confidence than usage estimates. A measurement stores gross, the exact tare used, net, expected-before, variance, confirmation, source, operator, and time. Unknown imported tare is established atomically with the first verified measurement. Historical usage is never rewritten.

Spoolman reconciliation accepts only supported API data. Decreases create immutable usage events and update effective expected mass; identity-sensitive remote changes remain canonical in Filament Manager. Projection updates read and merge Spoolman `extra` fields so another integration's keys are preserved.

## Security boundaries

- Local passwords use Argon2id; no default user exists.
- Browser sessions are random, hashed server-side, revocable, HttpOnly, SameSite Strict, CSRF-bound, and time-limited.
- Role checks are server-side on every route.
- Configuration rejects credentials embedded in integration URLs.
- Database URLs, API keys, and service-account documents come from restricted files or Docker secrets.
- Trusted hosts, exact CORS origins, security headers, sanitized API errors, login throttling, and least-privilege containers are enabled.
- Spoolman has no built-in authentication; keep its LAN endpoint firewalled and put remote browser access behind an authenticated proxy.
- Workstation agents have no listener. Pairing codes expire after ten minutes and are consumed once; long-lived agent credentials are stored as hashes and authorize only agent heartbeat, claim, and completion routes.
- Cura writes occur only while Cura is closed, under verified discovered data roots, with symlink/root-escape rejection, automatic backups, checksums, atomic replacement, and rollback.

## Repository map

- `src/filament_manager/`: API, domain policy, models, clients, import, and workers
- `migrations/`: reversible Alembic schema history
- `frontend/`: React/TypeScript application and Playwright checks
- `workstation-agent/`: Arch Linux and Windows 11 Cura discovery, installers, deployment writer, and agent tests
- `docker/`: local Compose, independent production stacks, and database provisioning
- `integrations/`: Moonraker and Klipper examples
- `docs/specification/`: complete imported source documentation
- `mappings/`, `schemas/`, `reference/`: import contracts and original workbook fixture
- `skills/`: focused agent procedures indexed by `AGENTS.md`
