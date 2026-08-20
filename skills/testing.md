# Testing and Validation Skill

Before handoff, run the checks relevant to the changed surface:

```bash
ruff check .
ruff format --check .
mypy src
pytest
pip-audit --skip-editable
npm run lint --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
npm audit --prefix frontend
docker build -t filament-manager:validation .
pip install -e './workstation-agent[dev]'
ruff check workstation-agent/src workstation-agent/tests
mypy workstation-agent/src
pytest workstation-agent/tests
```

- Unit tests cover mass calculations, calibration invalidation, Spoolman extra-field merging, authentication policy, workbook integrity, and presentation formatting.
- Bugsnag tests cover default-off and malformed configuration, lazy browser loading, React fallback behavior, final-delivery sanitization, normalized routes, private-origin removal, polling-span suppression, terminal-worker throttling, exact Content Security Policy destinations, authorized source-map configuration, and absence of source maps from runtime images. Never send a real test event from routine automated tests.
- PostgreSQL integration tests cover the unknown-tare measurement, immutable history, audit, and outbox transaction.
- Print tests cover bounded Cura/Moonraker parsing, decimal-tolerant mismatch evidence, warn/block release behavior, `complete`/`completed` convergence, exact snapshot timing after preflight, live/history deduplication, M600 segment usage, append-only assessments, legacy unresolved imports, and success-statistics latest revisions.
- Terminal print-use tests cover completed, failed, and cancelled outcomes, actual-only segment weight, recurring M600 spools aggregated once, idempotent repeat polling, and protection against double subtraction after Spoolman usage import.
- Account/notification tests cover empty-database `admin` / `admin` creation, forced first-login password replacement, singleton identity/password edits, other-session revocation, removed multi-account endpoints, per-user reads, recurrence becoming unread, and deduplicated category resolution.
- Build-plate tests cover immutable maintenance events, configurable day/print due thresholds, cleaning and per-side mesh actions, physical mesh clearing before canonical context is cleared, and bounded metadata-stripped WebP upload/replacement/deletion.
- Version 0.2.2 inventory tests cover physical nozzle CRUD/install/remove attribution, manual duplicate-safe Side B creation and unavailable state, completed plate/nozzle/distinct-spool counts including M600 segments, persisted diagnostics validation, and safe projection rebuild queues.
- Diagnostics regression tests cover the current Alembic head, authenticated text-download headers and bounded content, SQL/URL sanitization, stale-agent guidance, safe Moonraker sub-operation failure summaries, and recurring dead-job supersession.
- Connector contract tests mock supported Spoolman endpoints and verify remote `extra` fields survive updates.
- Playwright covers authenticated desktop navigation, theme switching, mobile unknown-tare weighing, multi-version profile comparison, build-plate maintenance controls, exact print detail/scoring, notifications, and mobile print/data cards.
- Rendered UI validation compares implementation screenshots with `docs/design/concepts/` in both themes and at a mobile viewport.
- Workstation-agent tests use isolated temporary Cura roots and cover machine discovery, hardened approved-key material import, bounded saved print-profile global/first-extruder merging, expression omission, complete desired-library XML/plugin rendering including the two-line filler/finish description and Klipper plugin keys, inert plugin registration until `initializationFinished`, automatic Material Settings visible-key alignment, renderer-revision invalidation with an unchanged server checksum, bundled-choice filtering, exclusive user-material replacement, root/symlink rejection, idempotent apply, drift detection, backup, and rollback.
- Cura recovery tests cover closed-process capture, exact-version matching, secret/endpoint/path removal, semantic plugin inventory, snapshot deduplication and ten-point retention, reset protection, Administrator confirmation, lease/deferral/completion, exclusive allowlisted profile replacement, safe preference merging that preserves current login/network secrets, local backup, rollback, Diagnostics status, and managed-library requeue.
- Workstation HTTP-client tests verify that pairing and service requests use a hostname-verifying operating-system TLS context rather than an isolated bundled public CA file or an insecure verification bypass.
- Installer tests run the Arch and PowerShell standalone paths twice with isolated per-user state to prove explicit fresh/upgrade output, code replacement, pairing preservation, and conditional restart behavior. Uninstaller checks prove scoped service/task and private-root removal without touching Cura files. Keep ShellCheck and PowerShell parser validation in the workstation release checks.
- Cura takeover tests cover reported material files and saved print profiles including zero-literal/expression-only sources, the two-stage mapping dialog and its back action, optional source-to-existing-template mappings, source/template uniqueness, ignored sources, semantic reviewed-source catalog conflicts without heartbeat-version races, atomic confirmation, direct template saves, linked-profile inheritance, repeated-takeover rejection, and the server-side takeover guard.
- Configured-system seed tests prove the recommended ASA template and immutable starting snapshot are created once per printer/nozzle scope and never overwrite an existing ASA template.
- Profile-inheritance tests cover decimal-equivalent sparse overrides, extension removal, resolved snapshots, inherited-value fallback, customized-field highlighting, canonical Cura alias controls, per-setting reset, preserved override ownership across direct template saves, and immediate propagation to every linked filament.
- Managed Cura edit tests cover known template/profile GUIDs, semantic no-op filtering, idempotent receipts, direct current-state saves, unknown GUID rejection, and canonical resynchronization after capture.
- PostgreSQL integration tests cover single-use pairing, hashed scoped credentials, agent-specific lease claiming, and audited deployment completion.
- Deployment-contract tests keep the `filament_user`/`spoolman_user` role split, explicit non-SSL settings, trusted-host-aware web probe, and disabled non-HTTP service health checks synchronized across `.env.example`, Compose, combined Swarm, and independent Swarm files.
- Build-plate tests cover exact Side A `P<number>` and Side B `P<number>b` validation, grouping/natural ordering, bounded Moonraker discovery, metadata preservation, per-side missing-mesh availability, automatic active-side alignment, the live saved-mesh macro chooser, and the absence of required manual synchronization controls.
- Moonraker tests cover the supported active Spoolman ID endpoint, persistent physical-spool macro state, separately bounded strict-print and safe-manual catalogs, exact-profile/template manual temperatures, live manual selection, guarded direct Spoolman target requests plus physical-ID restoration, 15-second state scheduling, 5-minute printer-information scheduling, and safe partial progress when one state request fails.
- Klipper reference tests parse every section and literal, balance Jinja control tags, enforce traditional `M600.1` renaming, confirm `START_PRINT`/`END_PRINT` remain undefined, and assert physical unload/load calls precede their Spoolman commit helpers. Also validate the file with Klipper's current Jinja delimiters when changing its templates and perform an idle-printer Fluidd test before deployment.
- Cura preflight tests require the server and workstation renderer to share the deterministic material GUID. Test matching bypass, zero/one/multiple eligible spool choices, stale or template-only materials, old/new temperatures, insertion timeout, cancellation before and after unload, recoverable M600/manual target selection, guarded direct Spoolman selection, and direct active-ID drift.
- Frontend tests and rendered Playwright checks cover the shared grouped editor, separate retract/prime speeds, the five visible cooling controls with silent zero initial fan, removal of fold-down record editors, automatic freshness copy, active-spool indicators, the **Load spool** request and pending Fluidd guidance, version presentation and release comparison, all eight Settings color profiles, simplified logout/collapse controls, keyboard focus containment, and desktop/mobile Build Plates and Printers layouts.
- Filament/spool frontend checks cover live inherited/customized highlighting, Cura-like group placement without a catch-all section, field-specific compact precision, the shared spool silhouette with distinct solid/multicolor/rainbow fills, inferred tare preview, full correction forms, current compatible-template selection, three-line product identity, controlled-input focus retention, color-history locking, and delete-or-archive copy.
- Spool-label tests require high QR error correction, a four-module quiet zone, and the largest independently decodable canonical solid, one/two/three-sample multicolor, or rainbow palette inside the centered spool icon. Before release, decode representative full-resolution and downscaled label images with an independent scanner.
- Cura material-setting documentation tests require the plain-text Material Settings plugin checklist to match every editable central catalog key and label exactly.
- PostgreSQL inventory tests cover inferred tare and initial measurement, true deletion of setup-only mistakes, archival with retained dependencies, operator remaining-mass corrections, locked post-use identities/colors, and matching Spoolman delete/upsert/weight outbox work.
- Material-comparison tests cover decimal normalization, difference-only core/additional Cura rows, two-to-four profile/template selections, matching scopes, cross-printer/nozzle warnings, exact-profile success rates, template N/A, low samples, and responsive desktop/mobile presentation.
- Spool-location tests cover whitespace normalization, explicit clearing, one-time legacy import from Spoolman, canonical drift repair, audit/outbox creation, and desktop/mobile editing.
- Spoolman contract tests cover managed-field provisioning, outer JSON encoding for text values, nested string serialization for structured display palettes, pagination, duplicate-safe UUID discovery, full canonical convergence, non-destructive usage ordering, canonical three-decimal mass normalization, and stale-job recovery. Validate contract-sensitive changes against the pinned real Spoolman image in addition to mocks.
