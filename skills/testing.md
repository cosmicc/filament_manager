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
- PostgreSQL integration tests cover the unknown-tare measurement, immutable history, audit, and outbox transaction.
- Connector contract tests mock supported Spoolman endpoints and verify remote `extra` fields survive updates.
- Playwright covers authenticated desktop navigation, theme switching, and the mobile unknown-tare weighing flow.
- Rendered UI validation compares implementation screenshots with `docs/design/concepts/` in both themes and at a mobile viewport.
- Workstation-agent tests use isolated temporary Cura roots and cover machine discovery, hardened approved-key material import, complete desired-library XML/plugin rendering including Klipper plugin keys, bundled-choice filtering, exclusive user-material replacement, root/symlink rejection, idempotent apply, drift detection, backup, and rollback.
- Installer tests run the Arch and PowerShell standalone paths twice with isolated per-user state to prove code replacement, pairing preservation, and conditional restart behavior. Keep ShellCheck and PowerShell parser validation in the workstation release checks.
- Cura material preservation tests cover reported workstation data, draft-template creation, source provenance, duplicate rejection, publication, and the server-side takeover guard.
- Profile-inheritance tests cover decimal-equivalent sparse overrides, extension removal, resolved snapshots, per-setting reset, preserved overrides across a new template base, and separate confirmation for each filament.
- Managed Cura edit tests cover known template/profile GUIDs, semantic no-op filtering, idempotent receipts, draft-only creation, unknown GUID rejection, and canonical redeployment after capture.
- PostgreSQL integration tests cover single-use pairing, hashed scoped credentials, agent-specific lease claiming, and audited deployment completion.
- Deployment-contract tests keep the `filament_user`/`spoolman_user` role split, explicit non-SSL settings, trusted-host-aware web probe, and disabled non-HTTP service health checks synchronized across `.env.example`, Compose, combined Swarm, and independent Swarm files.
- Build-plate tests cover exact Side A `P<number>` and Side B `P<number>b` validation, grouping/natural ordering, bounded Moonraker discovery, metadata preservation, per-side missing-mesh availability, automatic active-side alignment, macro selection, and the absence of required manual synchronization controls.
- Moonraker tests cover the supported active Spoolman ID endpoint, persistent physical-spool macro state, bounded catalog serialization, guarded change requests, physical-authority drift repair, 15-second state scheduling, 5-minute printer-information scheduling, and safe partial progress when one state request fails.
- Klipper reference tests parse every section and literal, balance Jinja control tags, enforce traditional `M600.1` renaming, confirm `START_PRINT`/`END_PRINT` remain undefined, and assert physical unload/load calls precede their Spoolman commit helpers. Also validate the file with Klipper's current Jinja delimiters when changing its templates and perform an idle-printer Fluidd test before deployment.
- Cura preflight tests require the server and workstation renderer to share the deterministic material GUID. Test matching bypass, zero/one/multiple eligible spool choices, stale or template-only materials, old/new temperatures, insertion timeout, cancellation before and after unload, M600 target selection, and direct active-ID drift.
- Frontend tests and rendered Playwright checks cover the shared grouped editor, removal of fold-down record editors, automatic freshness copy, active-spool indicators, the **Load spool** request and pending Fluidd guidance, keyboard focus containment, and desktop/mobile Build Plates and Printers layouts.
- Material-comparison tests cover decimal normalization, difference-only core/additional Cura rows, profile-to-profile selection, profile-to-template revision selection, matching scopes, cross-printer/nozzle warnings, and responsive desktop/mobile presentation.
- Spool-location tests cover whitespace normalization, explicit clearing, one-time legacy import from Spoolman, canonical drift repair, audit/outbox creation, and desktop/mobile editing.
- Spoolman contract tests cover managed-field provisioning, JSON-encoded custom values, pagination, duplicate-safe UUID discovery, full canonical convergence, non-destructive usage ordering, and stale-job recovery. Validate contract-sensitive changes against the pinned real Spoolman image in addition to mocks.
