# Cura Workstation Agent

## What it automates

Each Arch Linux or Windows 11 workstation runs one agent under the same user account as Cura. The agent automatically:

- discovers standard Cura, Flatpak, and Snap user-data locations on Arch Linux and `%APPDATA%\cura` on Windows;
- reports only version and machine metadata, never absolute workstation paths;
- receives published material-profile deployments through an outbound HTTPS poll;
- waits while Cura is open;
- matches the Filament Manager printer and nozzle to one Cura machine instance;
- installs an official-format `.xml.fdm_material` plus paired global and extruder `quality_changes` profiles;
- backs up every replaced file, writes same-filesystem temporary files, and atomically replaces targets;
- records checksums so repeated deployments are idempotent; and
- restores the backup automatically if any write fails.

Pressure advance is inserted as a clearly delimited `SET_PRESSURE_ADVANCE` block when the matched Cura machine already has a `machine_start_gcode` override. If Cura is inheriting unknown start G-code and has no local override, the agent installs the remaining profile and reports a warning instead of replacing inherited start G-code. Create/save a machine start-G-code override once in Cura to make later pressure-advance updates fully automatic.

## Server requirement

Use an HTTPS Filament Manager public URL. Plain HTTP pairing is accepted only for an explicit loopback development installation. The agent follows no HTTP redirects and validates the normal operating-system certificate trust store.

Apply the current database migration before pairing agents:

```bash
alembic upgrade head
```

## Arch Linux

Install as the normal Cura desktop user from a checked-out release:

```bash
./workstation-agent/installers/install-arch.sh
```

When using the standalone CI artifact, pass its binary path to avoid a local Python dependency:

```bash
./installers/install-arch.sh ./filament-manager-agent
```

In Filament Manager, open **Cura workstations**, create a pairing code, and then run the command printed by the installer. The code is entered at a hidden prompt. Start the service after pairing:

```bash
systemctl --user start filament-manager-agent.service
systemctl --user status filament-manager-agent.service
```

The hardened user unit writes only to supported Cura and agent data locations. If Cura uses a nonstandard location, add it to `ReadWritePaths` and set `FILAMENT_MANAGER_CURA_ROOTS` in a systemd user-service override.

## Windows 11

Open PowerShell as the normal Cura desktop user, not Administrator:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\workstation-agent\installers\install-windows.ps1
```

When using the standalone Windows CI artifact, pass the executable to avoid a local Python dependency:

```powershell
.\installers\install-windows.ps1 -BinaryPath .\filament-manager-agent.exe
```

Create a pairing code in **Cura workstations**, run the command printed by the installer, then start the per-user logon task:

```powershell
Start-ScheduledTask -TaskName 'Filament Manager Cura Agent'
```

## Use

Publish a profile, then select **Deploy to all Cura workstations** on the Material profiles page. The Cura workstations page shows discovery, last contact, deployment state, warnings, and failures. Close Cura when a deployment is pending; the agent retries without manual requeueing.

Useful local commands:

```text
filament-manager-agent scan
filament-manager-agent status
filament-manager-agent run-once
filament-manager-agent rollback DEPLOYMENT_UUID
```

Rollback changes only files captured by that deployment's backup. It never deletes or rewrites unrelated Cura profiles.

## Security and removal

Pairing codes expire after ten minutes and work once. The server stores hashes of pairing codes and agent credentials, not plaintext. Revoke an agent in the web interface before decommissioning a workstation, then remove its scheduled task or systemd user unit and its private configuration directory.
