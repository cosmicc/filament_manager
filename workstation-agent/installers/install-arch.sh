#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -eq 0 ]]; then
  echo "Run this installer as the Cura desktop user, not root." >&2
  exit 1
fi

script_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_root=$(cd -- "${script_directory}/.." && pwd)
agent_root="${XDG_DATA_HOME:-${HOME}/.local/share}/filament-manager-agent"
state_root="${XDG_DATA_HOME:-${HOME}/.local/share}/Filament Manager Agent"
config_root="${XDG_CONFIG_HOME:-${HOME}/.config}/Filament Manager Agent"
unit_directory="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
unit_path="${unit_directory}/filament-manager-agent.service"
binary_path=${1:-}
service_was_active=false
staged_path=""
backup_path=""
existing_installation=false

if [[ -e ${unit_path} || -e ${agent_root}/filament-manager-agent || -d ${agent_root}/venv ]]; then
  existing_installation=true
  echo "Filament Manager Agent upgrade started. Existing pairing, state, and backups will be preserved."
else
  echo "Filament Manager Agent fresh installation started."
fi

cleanup() {
  local exit_status=$?
  if [[ ${exit_status} -ne 0 && -n ${backup_path} && -e ${backup_path} ]]; then
    if [[ -d ${backup_path} ]]; then
      rm -rf -- "${agent_root}/venv"
      mv -- "${backup_path}" "${agent_root}/venv"
    else
      mv -f -- "${backup_path}" "${agent_root}/filament-manager-agent"
    fi
  fi
  if [[ -n ${staged_path} && -e ${staged_path} ]]; then
    rm -rf -- "${staged_path}"
  fi
  if [[ ${exit_status} -ne 0 && ${service_was_active} == true ]]; then
    systemctl --user start filament-manager-agent.service >/dev/null 2>&1 || true
  fi
  exit "${exit_status}"
}
trap cleanup EXIT

# systemd must see these paths before it creates the service's read-only home
# namespace. ReadWritePaths cannot make a missing path writable after startup.
mkdir -p "${agent_root}" "${state_root}" "${config_root}" "${unit_directory}"
chmod 0700 "${agent_root}" "${state_root}" "${config_root}"
if [[ -n ${binary_path} ]]; then
  [[ -f ${binary_path} ]] || { echo "Standalone agent binary not found: ${binary_path}" >&2; exit 1; }
  staged_path=$(mktemp "${agent_root}/.filament-manager-agent.XXXXXX")
  install -m 0755 "${binary_path}" "${staged_path}"
  agent_executable="${agent_root}/filament-manager-agent"
else
  command -v python3 >/dev/null 2>&1 || { echo "Python 3.12 or newer is required." >&2; exit 1; }
  python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' || {
    echo "Python 3.12 or newer is required." >&2
    exit 1
  }
  agent_executable="${agent_root}/venv/bin/filament-manager-agent"
fi

if systemctl --user is-active --quiet filament-manager-agent.service; then
  service_was_active=true
  systemctl --user stop filament-manager-agent.service
fi

if [[ -n ${binary_path} ]]; then
  if [[ -e ${agent_executable} ]]; then
    backup_path="${agent_root}/.filament-manager-agent.backup"
    rm -f -- "${backup_path}"
    mv -- "${agent_executable}" "${backup_path}"
  fi
  mv -- "${staged_path}" "${agent_executable}"
  staged_path=""
else
  if [[ ! -d ${agent_root}/venv ]]; then
    python3 -m venv "${agent_root}/venv"
  fi
  "${agent_root}/venv/bin/python" -m pip install --upgrade pip
  "${agent_root}/venv/bin/python" -m pip install --upgrade "${source_root}"
fi

staged_unit=$(mktemp "${unit_directory}/.filament-manager-agent.service.XXXXXX")
sed \
  -e "s|@@AGENT_EXECUTABLE@@|${agent_executable}|g" \
  "${source_root}/installers/filament-manager-agent.service.in" \
  > "${staged_unit}"
chmod 0600 "${staged_unit}"
mv -f -- "${staged_unit}" "${unit_path}"

systemctl --user daemon-reload
systemctl --user enable filament-manager-agent.service

if [[ -n ${backup_path} && -e ${backup_path} ]]; then
  rm -rf -- "${backup_path}"
  backup_path=""
fi
if [[ ${existing_installation} == true && ${service_was_active} == true ]]; then
  systemctl --user start filament-manager-agent.service
  echo "Filament Manager Agent upgrade complete. The existing user service was restarted."
elif [[ ${existing_installation} == true ]]; then
  echo "Filament Manager Agent upgrade complete. The service was not running before the upgrade, so it remains stopped."
else
  echo "Filament Manager Agent fresh installation complete."
  echo "Pair this new installation:"
  echo "  ${agent_executable} pair --server https://YOUR-SERVER --name \"Arch Cura\""
  echo "Then run: systemctl --user start filament-manager-agent.service"
fi
