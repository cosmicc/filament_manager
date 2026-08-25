"""Cross-platform installer upgrade and configuration-preservation tests."""

# These tests intentionally execute only repository-controlled installers and temporary fixtures.
# PowerShell mock definitions remain on one line where that keeps the harness readable.
# ruff: noqa: E501, S603

import os
import shutil
import subprocess
from pathlib import Path

import pytest

INSTALLERS = Path(__file__).parents[1] / "installers"


def _write_executable(path: Path, marker: str) -> None:
    path.write_text(f"#!/usr/bin/env sh\nprintf '%s\\n' '{marker}'\n", encoding="utf-8")
    path.chmod(0o755)


def test_arch_installer_rerun_upgrades_and_restarts_active_service(tmp_path: Path) -> None:
    """A second standalone install replaces code but keeps pairing configuration."""

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    service_state = tmp_path / "service-state"
    service_log = tmp_path / "systemctl.log"
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "${FAKE_SYSTEMCTL_LOG}"
if [[ $* == *"is-active --quiet"* ]]; then
  [[ -f ${FAKE_SYSTEMCTL_STATE} && $(<"${FAKE_SYSTEMCTL_STATE}") == active ]]
elif [[ $* == *" stop "* ]]; then
  printf 'inactive' > "${FAKE_SYSTEMCTL_STATE}"
elif [[ $* == *" start "* ]]; then
  printf 'active' > "${FAKE_SYSTEMCTL_STATE}"
fi
""",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    first_binary = tmp_path / "agent-v1"
    second_binary = tmp_path / "agent-v2"
    _write_executable(first_binary, "version-one")
    _write_executable(second_binary, "version-two")
    user_config = tmp_path / "config" / "Filament Manager Agent" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text('{"agent_token":"preserve-me"}\n', encoding="utf-8")
    user_config.chmod(0o600)
    environment = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "FAKE_SYSTEMCTL_LOG": str(service_log),
        "FAKE_SYSTEMCTL_STATE": str(service_state),
    }
    installer = INSTALLERS / "install-arch.sh"

    first = subprocess.run(
        [str(installer), str(first_binary)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    service_state.write_text("active", encoding="utf-8")
    second = subprocess.run(
        [str(installer), str(second_binary)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    installed = tmp_path / "data" / "filament-manager-agent" / "filament-manager-agent"
    assert subprocess.check_output([str(installed)], text=True).strip() == "version-two"
    assert "fresh installation started" in first.stdout
    assert "fresh installation complete" in first.stdout
    assert "upgrade started" in second.stdout
    assert "existing user service was restarted" in second.stdout
    assert "--user stop filament-manager-agent.service" in service_log.read_text(encoding="utf-8")
    assert "--user start filament-manager-agent.service" in service_log.read_text(encoding="utf-8")
    assert user_config.read_text(encoding="utf-8") == '{"agent_token":"preserve-me"}\n'
    assert user_config.stat().st_mode & 0o777 == 0o600
    private_state = tmp_path / "data" / "Filament Manager Agent"
    assert private_state.is_dir()
    assert private_state.stat().st_mode & 0o777 == 0o700
    installed_unit = tmp_path / "config" / "systemd" / "user" / "filament-manager-agent.service"
    unit_text = installed_unit.read_text(encoding="utf-8")
    assert 'ReadWritePaths="%h/.config/Filament Manager Agent"' in unit_text
    assert '"%h/.local/share/Filament Manager Agent"' in unit_text

    removed = subprocess.run(
        [str(INSTALLERS / "uninstall-arch.sh")],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert "uninstall complete" in removed.stdout
    assert not (tmp_path / "data" / "filament-manager-agent").exists()
    assert not (tmp_path / "data" / "Filament Manager Agent").exists()
    assert not user_config.parent.exists()
    assert not (tmp_path / "config" / "systemd" / "user" / "filament-manager-agent.service").exists()


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is not installed")
def test_windows_installer_rerun_upgrades_and_restarts_active_task(tmp_path: Path) -> None:
    """The Windows installer replaces a running standalone agent without re-pairing."""

    first_binary = tmp_path / "agent-v1.exe"
    second_binary = tmp_path / "agent-v2.exe"
    first_binary.write_text("version-one", encoding="utf-8")
    second_binary.write_text("version-two", encoding="utf-8")
    harness = tmp_path / "installer-test.ps1"
    harness.write_text(
        """param([string]$Installer, [string]$Uninstaller, [string]$FirstBinary, [string]$SecondBinary, [string]$Root)
$ErrorActionPreference = 'Stop'
$env:LOCALAPPDATA = Join-Path $Root 'local-app-data'
$env:USERNAME = 'test-user'
$global:TaskState = $null
$global:Stops = 0
$global:Starts = 0
$global:Unregisters = 0
function Get-ScheduledTask { param($TaskName, $ErrorAction) if ($global:TaskState) { [pscustomobject]@{ State = $global:TaskState } } }
function Stop-ScheduledTask { param($TaskName) $global:Stops += 1; $global:TaskState = 'Ready' }
function Start-ScheduledTask { param($TaskName, $ErrorAction) $global:Starts += 1; $global:TaskState = 'Running' }
function Unregister-ScheduledTask { param($TaskName, [switch]$Confirm) $global:Unregisters += 1; $global:TaskState = $null }
function Unblock-File { param($LiteralPath, $ErrorAction) }
function New-ScheduledTaskAction { param($Execute, $Argument) [pscustomobject]@{ Execute = $Execute; Argument = $Argument } }
function New-ScheduledTaskTrigger { param([switch]$AtLogOn, $User) [pscustomobject]@{} }
function New-ScheduledTaskPrincipal { param($UserId, $LogonType, $RunLevel) [pscustomobject]@{} }
function New-ScheduledTaskSettingsSet { param($RestartCount, $RestartInterval, $ExecutionTimeLimit) [pscustomobject]@{} }
function Register-ScheduledTask { param($TaskName, $Action, $Trigger, $Principal, $Settings, [switch]$Force) $global:TaskState = 'Ready'; [pscustomobject]@{} }
$pairing = Join-Path $env:LOCALAPPDATA 'Filament Manager Agent/config.json'
New-Item -ItemType Directory -Path (Split-Path -Parent $pairing) -Force | Out-Null
Set-Content -LiteralPath $pairing -Value '{"agent_token":"preserve-me"}' -NoNewline
& $Installer -BinaryPath $FirstBinary -SkipPairing -SkipPathUpdate
& $Installer -BinaryPath $SecondBinary -SkipPairing -SkipPathUpdate
$installed = Join-Path $env:LOCALAPPDATA 'FilamentManagerAgent/filament-manager-agent.exe'
if ((Get-Content -LiteralPath $installed -Raw) -ne 'version-two') { throw 'Agent was not upgraded.' }
if ((Get-Content -LiteralPath $pairing -Raw) -ne '{"agent_token":"preserve-me"}') { throw 'Pairing changed.' }
if ($global:Stops -ne 1 -or $global:Starts -ne 2) { throw 'A fresh paired task and its upgrade were not started exactly once each.' }
& $Uninstaller -SkipPathCleanup
if (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'FilamentManagerAgent')) { throw 'Install root was not removed.' }
if (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'Filament Manager Agent')) { throw 'Private root was not removed.' }
if ($global:Unregisters -ne 1) { throw 'Scheduled task was not unregistered exactly once.' }
""",
        encoding="utf-8",
    )

    powershell = shutil.which("pwsh")
    assert powershell is not None
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-File",
            str(harness),
            "-Installer",
            str(INSTALLERS / "install-windows.ps1"),
            "-Uninstaller",
            str(INSTALLERS / "uninstall-windows.ps1"),
            "-FirstBinary",
            str(first_binary),
            "-SecondBinary",
            str(second_binary),
            "-Root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_uninstallers_remove_only_scoped_agent_paths() -> None:
    """Both uninstallers target the per-user agent service and private roots."""

    arch = (INSTALLERS / "uninstall-arch.sh").read_text(encoding="utf-8")
    assert "systemctl --user disable filament-manager-agent.service" in arch
    assert 'rm -rf -- "${target}"' in arch
    assert "Managed Cura materials and plugins were left in place" in arch
    assert 'rm -rf -- "${HOME}' not in arch

    windows = (INSTALLERS / "uninstall-windows.ps1").read_text(encoding="utf-8")
    assert "Unregister-ScheduledTask -TaskName $TaskName" in windows
    assert "Remove-Item -LiteralPath $Target -Recurse -Force" in windows
    assert "Managed Cura materials and plugins were left in place" in windows

    workflow = (
        Path(__file__).parents[2] / ".github" / "workflows" / "workstation-agent-build.yml"
    ).read_text(encoding="utf-8")
    assert "workstation-agent/installers/uninstall-arch.sh" in workflow
    assert "workstation-agent/installers/uninstall-windows.ps1" in workflow
