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
- PostgreSQL integration tests cover single-use pairing, hashed scoped credentials, agent-specific lease claiming, and audited deployment completion.
- Deployment-contract tests keep the `filament_user`/`spoolman_user` role split, explicit non-SSL settings, trusted-host-aware web probe, and disabled non-HTTP service health checks synchronized across `.env.example`, Compose, combined Swarm, and independent Swarm files.
- Build-plate tests cover exact Side A `P<number>` and Side B `P<number>b` validation, grouping/natural ordering, bounded Moonraker discovery, metadata preservation, per-side missing-mesh availability, active-side alignment, macro selection, and Administrator-only synchronization.
- Spool-location tests cover whitespace normalization, explicit clearing, one-time legacy import from Spoolman, canonical drift repair, audit/outbox creation, and desktop/mobile editing.
