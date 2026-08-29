# Architecture

## Authority model

Filament Manager uses PostgreSQL as the only canonical business database. The supplied workbook is a hash-bound initial import source, not an ongoing database. Google Sheets is a one-way protected publication. Standalone Spoolman is the printer-facing operational projection and usage source; Filament Manager never reads or writes Spoolman tables.

```text
Browser -> FastAPI -> filament_manager PostgreSQL
                    -> transactional outbox -> worker -> Spoolman REST API
                                                  |----> Moonraker HTTP API
                                                  `----> Google Sheets API

Cura workstation agent -> outbound HTTPS polling -> FastAPI -> leased desired library
                     |                        `-> sanitized recovery snapshots
                     `-> local backup -> atomic material/plugin/profile recovery

Cura -> bounded G-code inspection -> Klipper physical-spool preflight -> Moonraker/Spoolman
Fluidd -> exact spool and insertion confirmations ---^
Moonraker live/history and file APIs -> exact canonical print snapshots
```

The default production deployment operates Spoolman and Filament Manager as separate services in one Swarm stack. The stack creates a private `filament-services` overlay, while Moonraker uses Spoolman's stable published LAN address. Separate application stack files remain available when independent deployment lifecycles are required. Both layouts use remote PostgreSQL with isolated databases and roles.

Docker services build their validated runtime configuration directly from stack environment variables. No application configuration file is mounted. The current Docker contract accepts one Moonraker printer and derives its WebSocket endpoint from its HTTP base URL unless an explicit override is supplied.

Optional Bugsnag monitoring is a non-canonical outbound observability path. When enabled, FastAPI and worker processes use an isolated reporter and the browser receives a minimal non-cacheable runtime configuration before the React application loads. The browser reporter, React error boundary, and performance instrumentation are loaded dynamically only in enabled deployments. A final delivery filter strips private application data; route names and a narrow operational metadata allowlist provide grouping without URLs, raw messages, request data, user identity, or hostname. Diagnostics and local structured logs remain the full operational record.

Production frontend builds create hidden source maps for authorized CI upload and remove every map before the runtime image is assembled. The browser rewrites private asset origins while preserving asset paths, and the upload uses a wildcard asset base so one self-hosted build remains symbolizable across operator-selected hostnames.

## Canonical domains

- one local Administrator identity and revocable sessions
- Vendors, globally remembered named color samples, Filament Products, uniquely labeled Spools, and immutable physical Measurements
- immutable Spool Usage Events imported from supported Spoolman state
- Printers, installable physical Nozzles with lifecycle history, physical Build Plates, and printable sides; `P4` is Side A and `P4b` is Side B of physical plate P4
- versioned Material Profiles and resumable seven-step Calibration Sessions
- immutable Print Jobs, Material Segments, and append-only Outcome Assessments
- append-only Build Plate Maintenance Events, operational Settings, and persistent per-user Notifications
- append-only Audit Events, transactional Outbox Jobs, Projection State, persisted Diagnostic Runs, and Worker Heartbeats
- directly saved Material Templates, linked sparse product overrides with immutable resolved Material Profile snapshots, revocable Workstation Agents, single-use Pairing Codes, takeover mappings, managed-edit receipts, immutable desired-library synchronization snapshots, sanitized Cura Recovery Snapshots, and leased Cura Recovery Restores
- future authenticated Device adapters and identifier-only NFC mappings

Mass, density, dimensions, calibration factors, and money use PostgreSQL `NUMERIC`. Technical identities use UUIDs. Mutable rows use optimistic integer record versions. Times are stored in UTC and presented in America/Detroit.

## Mutation and synchronization rules

A canonical change, its audit record, and all required projection jobs commit in one transaction. Workers claim jobs with `FOR UPDATE SKIP LOCKED`, retry with bounded exponential backoff capped at each periodic job's normal poll interval, and never expose payloads or secrets in logs. PostgreSQL transaction advisory locks coordinate periodic scheduling across workers.

Physical measurements have higher confidence than usage estimates. A measurement stores gross, the exact tare used, net, expected-before, variance, confirmation, source, operator, and time. Unknown imported tare is established atomically with the first verified measurement. Historical usage is never rewritten.

Spoolman reconciliation accepts only supported API data. Decreases create immutable usage events and update effective expected mass; identity-sensitive remote changes remain canonical in Filament Manager. A legacy spool whose location ownership has never been established may adopt one existing, bounded Spoolman location. After import or any local edit, Filament Manager owns that free-text bucket value and reconciliation repairs remote drift. Projection updates read and merge Spoolman `extra` fields so another integration's keys are preserved. Structured display metadata is compacted into a string before Spoolman's outer JSON encoding because managed custom fields are declared as text.

The persisted Klipper spool macro records the last completed physical unload/load boundary. While Cura is closed, the workstation agent backs up and atomically saves the preflight call, material GUID placeholder, temperatures, and `END_PRINT` in the matched machine's start/end scripts. A strict bounded current exact-profile catalog drives print preflight, while a separate bounded catalog supplies projected non-empty spools and safe profile/template temperatures for manual load and M600 prompts. Filament Manager owns public M600, load, and unload commands and calls the printer's unchanged physical motion through exact reserved internal load/unload names; only the existing public cancel routine is renamed and wrapped. The worker publishes both catalogs and seeds physical state once. Catalog publication has its own durable Diagnostics status, so a missing or outdated optional macro remains actionable without failing otherwise successful physical spool/plate reconciliation or accumulating recurring dead queue rows. A direct non-null Spoolman selection made while idle or waiting for a manual target opens a guarded Fluidd confirmation, after which the worker restores the persisted physical ID until adoption or load completes. Other drift is repaired immediately. Requested targets never become canonical or operationally active before the physical boundary advances.

The five-second print observer reads only supported Moonraker live/history and file APIs. Before spool selection it streams bounded G-code, hashes the complete accepted file, parses bounded Cura metadata without evaluation, and records mismatches. Warning mode retains evidence and continues; Administrator-enabled blocking pauses on missing profile state, unavailable inspection, or supported mismatches. Exact printer, physical nozzle, spool, product, profile, plate, and profile-setting state is captured only after preflight completes. Historical state is immutable, supported bounded raw Moonraker terminal outcomes replace stale in-progress display state, M600 changes append segments, and legacy records remain unresolved when evidence is unavailable. Each imported history row is isolated so malformed bounded legacy data cannot block valid records or the successful synchronization checkpoint. Matching moonraker-timelapse MP4 paths are stored as server-side references and streamed through an authenticated range-capable application endpoint, never as private Moonraker URLs or credentials. Completed-print statistics derive from these snapshots: a plate side and nozzle count once, and every distinct start/M600 spool counts once even if reused in more than one segment.

Notification detection runs server-side and deduplicates persistent operational conditions while maintaining per-user read state. Recurring conditions become unread again. An empty database creates the exact `admin` / `admin` Administrator and restricts it to password replacement until complete. Existing single-account credentials remain unchanged during upgrade; identity or password edits revoke other sessions, and startup fails if incompatible legacy data contains more than one account.

Administrator-triggered build-plate synchronization reads Moonraker's supported `bed_mesh` printer object before opening its short canonical transaction. Exact bounded `P<number>` and `P<number>b` profiles create physical plates and sides, missing meshes update side availability without deleting metadata, and a loaded matching mesh updates the printer's active physical plate and side. `SELECT_BUILD_PLATE` without a parameter builds its Fluidd prompt live from the same saved mesh dictionary. An Operator may create the sole canonical Side B from an existing plate; its server-derived `P<number>b` side starts unavailable until that exact mesh is discovered. All other profile names are ignored.

Administrator-triggered printer information synchronization reads documented server/printer information plus the `configfile.settings` and `toolhead` objects. It records bounded versions, hostname, kinematics, nozzle diameter, and build volume without returning connection URLs or replacing manually maintained hardware descriptions.

The Diagnostics API assembles sanitized connection, synchronization, worker-heartbeat, actionable queue summaries, retry count/next-attempt context, one latest cause per failing job type, bounded recent-error, running/latest-version, Cura recovery-readiness, and canonical-database backup status. The browser never lists individual recent projection jobs. Scheduling a replacement periodic run first supersedes its older terminal row; a later successful recurring operation also retires older manual dead runs of that same reconstructable type. A newer equivalent object projection or full Spoolman convergence retires obsolete reconstructable upserts, while deletes and explicit weight adjustments remain actionable. Explicit net-weight corrections use the supported Spoolman remaining-weight update and are coalesced per spool during upgrade recovery. The version comparison queries only the fixed public GitHub releases endpoint, includes non-draft testing releases, caches results, and suppresses upstream response bodies. Read-only validation results are persisted for review. An Administrator-triggered projection rebuild creates idempotent Spoolman, Google, and managed Cura outbox work without modifying canonical inventory or acting as a database restore.

The worker also coordinates automatic logical backups with a dedicated PostgreSQL advisory lock. A private ZIP contains exactly one custom-format dump and one checksummed manifest and is written atomically into the shared application data volume. Diagnostics manages schedule, automatic retention, trusted download/import, and exact restore preparation. Restoration remains outside the live web/worker boundary: the zero-replica maintenance service creates a safety archive, applies the selected dump in one transaction, upgrades forward, revokes browser sessions, and records recovery before normal services resume. Spoolman's separately credentialed database never crosses this boundary.

While Cura is closed, the workstation agent captures a bounded exact-version operational configuration: complete non-sensitive printer/extruder/definition-change documents including start/end G-code and machine options, user definitions and variants, custom quality state, setting visibility, approved preferences, safe Cura2Moonraker behavior choices, and a semantic plugin inventory. It strips account sessions, credentials, endpoints, local paths, and plugin code before upload. The server stores at most fifteen automatic points per workstation installation and Cura version; named points are retained separately until explicit deletion. It content-deduplicates automatic captures, audits metadata edits/deletions, and rejects apparent reset/deletion automatic captures so they cannot replace the last known-good point. An explicit named request may preserve the current reset state separately, and Cura Workstations shows its live sanitized lifecycle. A confirmed Administrator restore is leased only to the originating workstation and exact reported Cura version. The agent takes a local rollback backup, atomically replaces the allowlisted configuration, and merges safe preferences without disturbing current login/connection secrets. The server then queues canonical extruder-nozzle alignment before normal material synchronization restores the library. On every heartbeat the agent reports the exact linked position-zero extruder nozzle value separately from machine metadata so the server can reconcile later drift. On the next safe Cura initialization, the managed plugin aligns and continuously repairs the Material Settings plugin's enabled-setting preference from the central catalog, verifies the active definitions, and writes a manifest-bound value-free receipt that the agent publishes to Cura Workstations and Diagnostics.

## Security boundaries

- Local passwords use Argon2id. The accepted first-install `admin` / `admin` default exists only on an empty database and is forced through password replacement before other access.
- Browser sessions are random, hashed server-side, revocable, HttpOnly, SameSite Strict, CSRF-bound, and time-limited.
- Role checks are server-side on every route.
- Configuration rejects credentials embedded in integration URLs.
- Optional Bugsnag reporting is default-off, uses only the SDK API key at runtime, confines the separate Upload API key to source-map CI, permits exact delivery hosts in the Content Security Policy only while enabled, and removes raw/private values again in a final delivery callback. Browser trace propagation is disabled and high-frequency polling spans are discarded.
- Database URLs, API keys, and service-account documents currently enter Docker services through scoped environment variables. Values remain masked in application models and must never be logged; populated `.env` files and Docker/Portainer operator access are tightly restricted.
- PostgreSQL connections explicitly disable TLS on the dedicated isolated database network. This exposes credentials and queries to network observers and must never be extended onto a shared or untrusted network.
- Trusted hosts, exact CORS origins, security headers, sanitized API errors, login throttling, and least-privilege containers are enabled.
- Spoolman has no built-in authentication; keep its LAN endpoint firewalled and put remote browser access behind an authenticated proxy.
- Workstation agents have no listener. Pairing codes expire after ten minutes and are consumed once; long-lived agent credentials are stored as hashes and authorize only agent heartbeat, claim, and completion routes.
- Cura writes occur only while Cura is closed, under verified discovered data/configuration roots, with symlink/root-escape rejection, automatic local rollback backups, content checksums, atomic desired-state replacement, bounded user custom-profile material-key cleanup, corrupt-profile quarantine, and rollback. Existing-material discovery uses hardened XML, saved print profiles use bounded non-interpolating INI parsing, and managed-edit intake accepts only approved keys, bounded payloads, deterministic known GUIDs, and no local paths. The one-time Administrator takeover maps any source subset to existing templates and applies the batch atomically. Managed edits save known current settings directly; unknown GUIDs and new Cura-created materials cannot enter canonical state. Product material cost uses a normalized weighted rate from current priced physical spools only when their currency agrees; the managed plugin merges that rate into Cura preferences without replacing unrelated material costs. Recovery uploads use a fixed directory/setting allowlist, per-file and aggregate bounds, exact-version checks, and conservative secret/endpoint/path filtering; raw paths, account state, credentials, private URLs, and plugin executables never leave the workstation. Cura main profiles remain local and unsynchronized during ordinary material sync; the managed plugin mirrors explicit selected-material values into the supported user layer so higher quality layers cannot supersede them.
- G-code filenames, metadata, history, and Cura payloads are untrusted and bounded. File content is streamed, never executed, and external response bodies are not returned or logged.
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
