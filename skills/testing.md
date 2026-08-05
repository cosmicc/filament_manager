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
- Workstation-agent tests use isolated temporary Cura roots and cover machine discovery, official-format rendering, pressure-advance guards, root/symlink rejection, idempotent apply, backup, and rollback.
- PostgreSQL integration tests cover single-use pairing, hashed scoped credentials, agent-specific lease claiming, and audited deployment completion.
