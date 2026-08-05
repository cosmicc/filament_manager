#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -eq 0 ]]; then
  echo "Run this installer as the Cura desktop user, not root." >&2
  exit 1
fi

script_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_root=$(cd -- "${script_directory}/.." && pwd)
agent_root="${XDG_DATA_HOME:-${HOME}/.local/share}/filament-manager-agent"
unit_directory="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
binary_path=${1:-}

mkdir -p "${agent_root}" "${unit_directory}"
if [[ -n ${binary_path} ]]; then
  [[ -f ${binary_path} ]] || { echo "Standalone agent binary not found: ${binary_path}" >&2; exit 1; }
  install -m 0755 "${binary_path}" "${agent_root}/filament-manager-agent"
  agent_executable="${agent_root}/filament-manager-agent"
else
  command -v python3 >/dev/null 2>&1 || { echo "Python 3.12 or newer is required." >&2; exit 1; }
  python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' || {
    echo "Python 3.12 or newer is required." >&2
    exit 1
  }
  python3 -m venv "${agent_root}/venv"
  "${agent_root}/venv/bin/python" -m pip install --upgrade pip
  "${agent_root}/venv/bin/python" -m pip install --upgrade "${source_root}"
  agent_executable="${agent_root}/venv/bin/filament-manager-agent"
fi

install -m 0600 /dev/null "${unit_directory}/filament-manager-agent.service"
sed \
  -e "s|@@AGENT_EXECUTABLE@@|${agent_executable}|g" \
  "${source_root}/installers/filament-manager-agent.service.in" \
  > "${unit_directory}/filament-manager-agent.service"

systemctl --user daemon-reload
systemctl --user enable filament-manager-agent.service

echo "Agent installed. Pair it before starting the service:"
echo "  ${agent_executable} pair --server https://YOUR-SERVER --name \"Arch Cura\""
echo "Then run: systemctl --user start filament-manager-agent.service"
