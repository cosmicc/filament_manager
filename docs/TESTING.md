# Testing

## Complete validation

From the repository root:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src
.venv/bin/pytest
.venv/bin/pip-audit --skip-editable
npm run lint --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
npm audit --omit=dev --prefix frontend
pip install -e './workstation-agent[dev]'
ruff check workstation-agent/src workstation-agent/tests
ruff format --check workstation-agent/src workstation-agent/tests
mypy workstation-agent/src
pytest workstation-agent/tests
docker build -t filament-manager:validation .
docker compose -f docker/docker-compose.yml config
```

`pytest` uses a disposable PostgreSQL 17 container for integration coverage. Docker must be available. SQLite is intentionally unsupported.

## Database migrations

Against an isolated PostgreSQL database, validate all three operations:

```bash
alembic upgrade head
alembic check
alembic downgrade base
alembic upgrade head
```

Never run downgrade validation against production data.

## Authenticated browser validation

Install the Chromium test browser once, then point Playwright at an isolated, migrated, seeded application:

```bash
npx playwright install chromium
FILAMENT_MANAGER_E2E_BASE_URL=http://127.0.0.1:8080 \
FILAMENT_MANAGER_E2E_USERNAME=validation-admin \
FILAMENT_MANAGER_E2E_PASSWORD='isolated-test-password' \
npm run test:e2e --prefix frontend
```

The test exercises login, dashboard, inventory navigation, themes, and the mobile unknown-tare weighing sheet. Rendered references are written to `docs/design/validation/`.

## Failure isolation

Before production, separately verify:

- Spoolman offline while canonical changes queue and retry
- Filament Manager offline while Moonraker continues updating Spoolman
- Google disabled or unavailable without blocking canonical writes
- duplicate measurement idempotency keys
- suspicious increases and above-nominal Administrator overrides
- re-running an earlier calibration step invalidates downstream completed results
- P1–P5 selection rejects all other codes
- pairing-code replay and disabled or cross-agent credentials
- Cura running during deployment, ambiguous machine/nozzle matches, symlink/root escapes, partial-write rollback, and idempotent reapply
