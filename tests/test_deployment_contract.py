"""Deployment-variable and database-isolation contract tests."""

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


def test_image_healthcheck_uses_the_trusted_host_aware_probe() -> None:
    """The image must probe readiness with the configured public hostname."""

    dockerfile = _read("Dockerfile")
    assert 'CMD ["python", "-m", "filament_manager.healthcheck"]' in dockerfile
    assert "urllib.request.urlopen('http://127.0.0.1:8080/health/ready'" not in dockerfile


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

    local_services = _read_yaml("docker/docker-compose.yml")["services"]
    assert local_services["bootstrap-admin"]["healthcheck"] == {"disable": True}
