# 19 - Testing Strategy

## Unit tests

- mass calculations and clamping
- purchase cost per gram and currency-safe Cura product-cost aggregation
- density/length calculations
- profile validation
- calibration dependency invalidation
- plate/mesh validation
- Google output escaping
- idempotency-key generation
- Spoolman extra-field merge
- deterministic Cura material GUIDs, merged managed cost preferences, separate bounded strict-print/manual-load catalogs, exact-profile/template load-temperature fallback, Klipper macro syntax, and physical unload/load commit ordering
- derived completed-print counts for one plate side, captured physical nozzle, and each distinct start/M600 spool
- manual Side B creation, duplicate rejection, and mesh-unavailable initial state
- Cura recovery path/setting allowlists, credential/endpoint/path removal, deterministic checksums, semantic plugin inventory, automatic and named captures, metadata edits, durable confirmed deletion, exact-version enforcement, reset detection, retention, local rollback, safe Cura2Moonraker behavior merging, and current connection-secret preservation
- Bugsnag opt-in validation, final-delivery sanitization, lazy browser loading, route normalization, polling suppression, exact Content Security Policy destinations, and duplicate worker throttling

## PostgreSQL integration tests

Use a real disposable PostgreSQL instance for:

- migrations
- numeric precision
- JSONB behavior
- advisory locks
- worker claiming with `SKIP LOCKED`
- outbox atomicity, exact failure timestamps, periodic replacement supersession, and reconstructable-versus-non-reconstructable recovery
- optimistic concurrency
- nozzle lifecycle events, one-installed-nozzle enforcement, worker heartbeats, and persisted diagnostic runs
- immutable Cura recovery snapshots, per-installation/version retention, idempotent upload, reset-blocked preservation, leased restore claims, and bounded completion state

## Connector tests

Mock or containerize:

- Spoolman REST and WebSocket
- Moonraker status, physical-spool macro state, bounded catalogs with non-fatal durable catalog errors, guarded change calls, direct Spoolman target capture/restoration, and live manual-load prompts
- running/latest-version comparison, testing-release inclusion, fixed GitHub endpoint behavior, caching, unavailable-state sanitization, and desktop/mobile presentation
- Google Sheets batch updates and quota failures

## End-to-end scenarios

1. Initial workbook import.
2. Manual weight entry updates canonical data, Spoolman, and Google.
3. Fluidd/Moonraker usage reduces remaining mass.
4. Spoolman offline and recovery with pending usage.
5. Google offline and later publication.
6. External Spoolman edit detected as drift.
7. Build plate `P3` selection loads mesh `P3`.
8. Calibration wizard directly applies results to the current profile.
9. Repeating temperature step invalidates dependent results.
10. Scale replay and unstable sample rejection.
11. NFC unknown tag and confirmed activation.
12. Matching Cura material bypasses the change workflow without altering the existing `START_PRINT` behavior.
13. Mismatched Cura material clears Spoolman only after unload and sets the selected ID only after load; cancellation at either prompt retains the last completed physical state.
14. `LOAD_FILAMENT`, `FILAMENT_MANAGER_LOAD_TARGET`, and a repeated M600 selection open the eligible catalog without a staged variable; a direct Spoolman selection is restored until confirmed; and `SELECT_BUILD_PLATE` enumerates only live valid P-number meshes.
15. Each selected Cura source maps to one existing template or remains ignored; one confirmation applies all mappings and linked-profile inheritance atomically before synchronization starts.
16. Read-only recovery validation persists sanitized results without changing canonical records, and projection rebuild queues complete derived work.
17. A completed print with repeated M600 segments counts each distinct spool once and its captured nozzle and plate side once.
18. A closed Cura installation captures a sanitized recovery point; a simulated reset cannot displace it; an Administrator-confirmed exact-version restore rolls back safely on write failure and is followed by canonical material synchronization.

## Swarm tests

- required stack variables reach only their intended services
- `filament_user`/`spoolman_user` and explicit non-SSL database settings match across all deployment surfaces
- overlay DNS resolution
- published 7912 reaches Spoolman target 8000
- service restart does not duplicate jobs
- rolling update does not run conflicting migrations
- optional Bugsnag variables reach web and worker only, source-map upload remains direct-push/secret-gated, and runtime images contain no source maps

## Restore test

Restore both PostgreSQL databases independently to an isolated environment, deploy both services in the combined stack, rebuild Spoolman projections through the API, rebuild a new Google Sheet, and verify that retained Cura recovery metadata remains available without exposing raw payloads to the browser. This is the definitive server disaster-recovery test. Test workstation recovery separately with the same Cura version and non-production account/connection state.

## Stack-boundary tests

- stop Filament Manager and verify Moonraker continues updating Spoolman
- redeploy Spoolman and verify Filament Manager reconnects and reconciles
- verify neither service receives the other service's database credential
- remove and recreate `filament-services`, then verify recovery
- test independent image rollback for each stack
- verify Moonraker never depends on Swarm-internal DNS

## Authoritative implementation references

- Spoolman repository and supported databases: https://github.com/Donkie/Spoolman
- Spoolman installation and Docker port mapping: https://github.com/Donkie/Spoolman/wiki/Installation
- Spoolman configuration variables: https://github.com/Donkie/Spoolman/blob/master/.env.example
- Spoolman REST API: https://donkie.github.io/Spoolman/
- Moonraker Spoolman configuration: https://moonraker.readthedocs.io/en/stable/configuration/#spoolman
- Moonraker Spoolman integration API: https://moonraker.readthedocs.io/en/latest/external_api/integrations/#spoolman
- Fluidd Spoolman support: https://docs.fluidd.xyz/features/spoolman
- Google Sheets API: https://developers.google.com/workspace/sheets/api
- Docker Swarm stack deployment: https://docs.docker.com/engine/swarm/stack-deploy/
- PostgreSQL documentation: https://www.postgresql.org/docs/
