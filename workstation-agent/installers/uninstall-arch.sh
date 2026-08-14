#!/usr/bin/env bash
set -euo pipefail

# Remove only the current user's Filament Manager Agent installation. Managed
# Cura materials are intentionally left in place so uninstalling cannot damage
# Cura's usable material library.
if [[ ${EUID} -eq 0 ]]; then
  echo "Run this uninstaller as the Cura desktop user, not root." >&2
  exit 1
fi

agent_root="${XDG_DATA_HOME:-${HOME}/.local/share}/filament-manager-agent"
state_root="${XDG_DATA_HOME:-${HOME}/.local/share}/Filament Manager Agent"
config_root="${XDG_CONFIG_HOME:-${HOME}/.config}/Filament Manager Agent"
unit_path="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user/filament-manager-agent.service"

echo "Filament Manager Agent uninstall started for the current user."
systemctl --user stop filament-manager-agent.service >/dev/null 2>&1 || true
systemctl --user disable filament-manager-agent.service >/dev/null 2>&1 || true

if [[ -f ${unit_path} ]]; then
  rm -f -- "${unit_path}"
fi
systemctl --user daemon-reload
systemctl --user reset-failed filament-manager-agent.service >/dev/null 2>&1 || true

for target in "${agent_root}" "${state_root}" "${config_root}"; do
  if [[ -d ${target} ]]; then
    rm -rf -- "${target}"
  fi
done

echo "Filament Manager Agent uninstall complete. The service, executable, pairing credential, local state, and agent backups were removed."
echo "Managed Cura materials and plugins were left in place. Revoke the workstation in Filament Manager if it still exists there."
