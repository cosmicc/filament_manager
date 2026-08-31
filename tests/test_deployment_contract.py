"""Deployment-variable and database-isolation contract tests."""

import ast
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    """Read one tracked deployment surface from the repository root."""

    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def _read_yaml(relative_path: str) -> dict[str, object]:
    """Parse one tracked Compose or Swarm deployment file."""

    return yaml.safe_load(_read(relative_path))


def test_database_clients_explicitly_disable_tls_with_expected_roles() -> None:
    """Every Docker path uses the approved roles and explicit non-SSL settings."""

    for relative_path in (
        "docker-stack.yml",
        "docker/filament-manager-stack.yml",
        "docker/docker-compose.yml",
    ):
        content = _read(relative_path)
        assert "${FILAMENT_MANAGER_DB_USERNAME:-filament_user}" in content
        assert "sslmode=${FILAMENT_MANAGER_DB_SSLMODE:-disable}" in content

    for relative_path in (
        "docker-stack.yml",
        "docker/spoolman-stack.yml",
        "docker/docker-compose.yml",
    ):
        content = _read(relative_path)
        assert "${SPOOLMAN_DB_USERNAME:-spoolman_user}" in content
        assert "${SPOOLMAN_DB_QUERY:-ssl=disable}" in content


def test_database_provisioning_owns_each_database_with_its_scoped_role() -> None:
    """Provisioning creates the canonical role names without cross-role grants."""

    provisioning_sql = _read("docker/provision-databases.sql")
    assert "'filament_manager', 'filament_user'" in provisioning_sql
    assert "'spoolman', 'spoolman_user'" in provisioning_sql
    assert "DATABASE filament_manager TO filament_user" in provisioning_sql
    assert "DATABASE spoolman TO spoolman_user" in provisioning_sql
    assert "DATABASE filament_manager TO spoolman_user" not in provisioning_sql
    assert "DATABASE spoolman TO filament_user" not in provisioning_sql

    local_initialization = _read("docker/postgres-init-databases.sh")
    assert "CREATE ROLE filament_user" in local_initialization
    assert "CREATE DATABASE filament_manager OWNER filament_user" in local_initialization
    assert "DATABASE filament_manager TO filament_user" in local_initialization


def test_example_environment_matches_the_database_contract() -> None:
    """The operator template exposes the same role and transport defaults."""

    values = {
        key: value
        for line in _read(".env.example").splitlines()
        if line and not line.startswith("#")
        for key, value in [line.split("=", 1)]
    }

    assert values["FILAMENT_MANAGER_DB_USERNAME"] == "filament_user"
    assert values["FILAMENT_MANAGER_DB_SSLMODE"] == "disable"
    assert values["SPOOLMAN_DB_USERNAME"] == "spoolman_user"
    assert values["SPOOLMAN_DB_QUERY"] == "ssl=disable"
    assert values["FILAMENT_MANAGER_DATABASE_AUTO_MIGRATE"] == "true"
    assert values["FILAMENT_MANAGER_DATABASE_MIGRATION_LOCK_TIMEOUT_SECONDS"] == "300"
    assert values["SPOOLMAN_RECONCILE_INTERVAL_MINUTES"] == "1"
    assert values["SYNC_OUTBOX_LOCK_TIMEOUT_SECONDS"] == "300"
    assert values["MOONRAKER_STATE_INTERVAL_SECONDS"] == "5"
    assert values["MOONRAKER_PRINT_INTERVAL_SECONDS"] == "5"
    assert values["MOONRAKER_INFO_INTERVAL_SECONDS"] == "300"
    assert values["BUGSNAG_ENABLED"] == "false"
    assert values["BUGSNAG_API_KEY"] == ""
    assert values["BUGSNAG_RELEASE_STAGE"] == "production"
    assert values["BUGSNAG_BROWSER_PERFORMANCE_ENABLED"] == "false"

    for relative_path in (
        "docker-stack.yml",
        "docker/filament-manager-stack.yml",
        "docker/docker-compose.yml",
    ):
        content = _read(relative_path)
        assert "${SPOOLMAN_RECONCILE_INTERVAL_MINUTES:-1}" in content
        assert "${SYNC_OUTBOX_LOCK_TIMEOUT_SECONDS:-300}" in content
        assert "${MOONRAKER_STATE_INTERVAL_SECONDS:-5}" in content
        assert "${MOONRAKER_PRINT_INTERVAL_SECONDS:-5}" in content
        assert "${MOONRAKER_INFO_INTERVAL_SECONDS:-300}" in content
        assert "${BUGSNAG_ENABLED:-false}" in content
        assert "${BUGSNAG_API_KEY:-}" in content
        assert "${BUGSNAG_RELEASE_STAGE:-production}" in content
        assert "${BUGSNAG_BROWSER_PERFORMANCE_ENABLED:-false}" in content


def test_source_maps_are_uploaded_only_by_authorized_ci_and_not_shipped() -> None:
    """Hidden source maps use the Actions secret and never remain in the runtime image."""

    workflow = _read(".github/workflows/ci.yml")
    dockerfile = _read("Dockerfile")
    vite_config = _read("frontend/vite.config.ts")

    assert "secrets.BUGSNAG_UPLOAD_API_KEY" in workflow
    assert "github.event_name == 'push'" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "BugsnagSourceMapUploaderPlugin" in vite_config
    assert "BugsnagBuildReporterPlugin" not in vite_config
    assert "sourcemap: 'hidden'" in vite_config
    assert "find dist -type f -name '*.map' -delete" in dockerfile


def test_multiarch_image_builds_frontend_on_native_builder_platform() -> None:
    """Static frontend assets must not run npm through target-platform emulation."""

    dockerfile = _read("Dockerfile")
    assert "FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend-build" in dockerfile


def test_image_healthcheck_uses_the_trusted_host_aware_probe() -> None:
    """The image must probe readiness with the configured public hostname."""

    dockerfile = _read("Dockerfile")
    assert 'CMD ["python", "-m", "filament_manager.healthcheck"]' in dockerfile
    assert "urllib.request.urlopen('http://127.0.0.1:8080/health/ready'" not in dockerfile


def test_image_runs_automatic_migrations_through_its_entrypoint() -> None:
    """Every long-running image command must pass through the migration coordinator."""

    dockerfile = _read("Dockerfile")
    assert 'ENTRYPOINT ["filament-manager-startup"]' in dockerfile
    assert 'filament-manager-startup = "filament_manager.startup:run"' in _read("pyproject.toml")
    for relative_path in (
        "docker-stack.yml",
        "docker/filament-manager-stack.yml",
        "docker/docker-compose.yml",
    ):
        content = _read(relative_path)
        assert "FILAMENT_MANAGER_DATABASE_AUTO_MIGRATE" in content
        assert "FILAMENT_MANAGER_DATABASE_MIGRATION_LOCK_TIMEOUT_SECONDS" in content

    assert "postgresql-client-18" in dockerfile
    assert "https://apt.postgresql.org/pub/repos/apt" in dockerfile


def test_non_http_services_disable_the_image_healthcheck() -> None:
    """Workers and local one-shot tools must not inherit the web HTTP probe."""

    for relative_path in (
        "docker-stack.yml",
        "docker/filament-manager-stack.yml",
        "docker/docker-compose.yml",
    ):
        deployment = _read_yaml(relative_path)
        services = deployment["services"]
        assert services["worker"]["healthcheck"] == {"disable": True}
        assert services["database-restore"]["healthcheck"] == {"disable": True}
        assert services["database-restore"]["command"] == [
            "filament-manager-cli",
            "restore-pending",
            "--confirm",
        ]

    local_services = _read_yaml("docker/docker-compose.yml")["services"]
    assert "bootstrap-admin" not in local_services
    assert local_services["database-restore"]["profiles"] == ["recovery"]

    for relative_path in ("docker-stack.yml", "docker/filament-manager-stack.yml"):
        restore_service = _read_yaml(relative_path)["services"]["database-restore"]
        assert restore_service["deploy"]["replicas"] == 0
        assert restore_service["deploy"]["restart_policy"] == {"condition": "none"}


def test_klipper_macro_variables_are_valid_python_literals() -> None:
    """Klipper parses every macro variable with ``ast.literal_eval`` at startup."""

    macro = _read("integrations/klipper/filament-manager-macros.cfg")
    variable_lines = [line for line in macro.splitlines() if line.casefold().startswith("variable_")]

    assert variable_lines
    assert 'variable_active_plate: "UNSET"' in variable_lines
    for line in variable_lines:
        _name, literal = line.split(":", 1)
        parsed_literal = ast.literal_eval(literal.strip())
        assert parsed_literal != "", "empty string macro defaults can be collapsed by config editors"
