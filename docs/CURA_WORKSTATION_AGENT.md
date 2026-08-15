# Cura Workstation Agent

## What it automates

Each Arch Linux or Windows 11 workstation runs one agent under the same user account as Cura. The agent automatically:

- discovers standard Cura, Flatpak, and Snap user-data locations on Arch Linux and `%APPDATA%\cura` on Windows;
- reports version, machine metadata, verified desired-library checksum, unmanaged import-source counts, and sanitized approved settings from existing materials and saved print profiles, never absolute workstation paths;
- receives the current `Template <material type>` entries and resolved product profiles as one desired-state library through an outbound HTTPS poll;
- reports approved setting edits to known managed material GUIDs so the server can save the corresponding current settings directly without accepting new Cura-created materials;
- waits while Cura is open;
- matches the Filament Manager printer and nozzle to one Cura machine instance;
- installs official-format `.xml.fdm_material` files plus the managed visibility plugin that hides bundled materials from Cura's selectors;
- backs up every added, replaced, or removed user material and managed-plugin file, writes same-filesystem temporary files, and atomically replaces targets;
- records a complete-library checksum so repeated synchronizations are idempotent and heartbeat drift is repaired; and
- restores the backup automatically if any write fails.

Install and enable the Cura **Material Settings** and **Klipper Settings** plugins. Filament Manager stores pressure advance as `klipper_pressure_advance_factor` and smooth time as the Klipper plugin's material settings. The agent never patches machine start G-code and never creates or changes quality profiles.

For physical-spool preflight, the operator must make the one-time Cura machine start-G-code change documented in [INSTALL.md](../INSTALL.md). The agent supplies each managed material's stable GUID but intentionally preserves the complete machine start/end G-code. Select a product material, not a `Template <material type>` entry, when sending a print that must resolve to physical inventory.

Existing Cura material files are parsed with a hardened XML parser. Saved print profiles under Cura's `quality_changes` directory are read without modification through a non-interpolating bounded parser; matching global and first-extruder layers are merged, explicit values from the extruder layer win, and Cura expressions are omitted rather than evaluated. Both paths report only the approved settings tracked by Filament Manager. Unsupported settings, additional extruders, file paths, machine settings, and start G-code are discarded.

On **Templates**, choose **Import from Cura**, or open **Cura workstations** directly. While the workstation says **Awaiting one-time takeover**, every reported material and saved print profile appears with a Filament Manager template selector. Choose the existing template each source should update, or leave it as **Do not import**. Each source and template may be used once. Review all mappings and the ignored count together, then select **Complete takeover** once. Filament Manager applies the mapped literal settings, updates linked profiles through normal inheritance, records provenance, enables management, and queues synchronization atomically. Unmapped user sources are backed up and then replaced by the managed library. Bundled files in Cura's installation remain untouched; the managed plugin hides them in material selectors.

After management is enabled, an edit to approved settings in an existing Filament Manager material is detected by its deterministic GUID and content checksum. The server saves that known template/profile directly and idempotently, preserves explicit filament customizations during template inheritance, and queues the current library for synchronization. Pre-takeover print-profile discovery does not continue as a source of canonical additions after management begins. New or copied Cura materials, changed identity metadata, unknown GUIDs, machine configuration, quality-profile changes, and start/end G-code are never imported. Add all new templates and filament products in Filament Manager.

## Server requirement

Use an HTTPS Filament Manager public URL. Plain HTTP pairing is accepted only for an explicit loopback development installation. The agent follows no HTTP redirects and validates the normal operating-system certificate trust store.

Docker web and worker startup automatically applies the workstation schema migration under the shared PostgreSQL advisory lock. Confirm both services are healthy before pairing agents.

## Arch Linux

Install as the normal Cura desktop user from a checked-out release:

```bash
./workstation-agent/installers/install-arch.sh
```

When using the standalone CI artifact, pass its binary path to avoid a local Python dependency:

```bash
./installers/install-arch.sh ./filament-manager-agent
```

Run the same installer again to upgrade an existing agent. It stages a standalone binary before
replacement, preserves the private pairing configuration and Cura backups, refreshes the user unit,
and restarts the service only when it was already running. A failed replacement restores the previous
standalone binary. Installer output explicitly identifies a fresh installation or an upgrade; an
inactive existing service remains stopped.

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

Run the same installer again to upgrade an existing agent. It stops a running per-user task before
replacement, preserves the private pairing configuration and Cura backups, refreshes the task, and
restarts it only when it was running before the upgrade. A failed standalone replacement restores the
previous executable. Installer output explicitly identifies a fresh installation or an upgrade; an
inactive existing task remains stopped.

Create a pairing code in **Cura workstations**, run the command printed by the installer, then start the per-user logon task:

```powershell
Start-ScheduledTask -TaskName 'Filament Manager Cura Agent'
```

## Use

Before takeover, open **Cura workstations** and wait for the agent to report existing material files and saved print profiles. Map any source you want to keep to an existing template and leave all others as **Do not import**. Use **Review takeover**, verify the mappings and ignored count, then select **Complete takeover**. A clean installation can complete with zero mappings. Cura shows bases as `Template PLA`, `Template PETG`, and so on under brand `Template`. Later template or product saves queue the complete library automatically. Close Cura when synchronization is pending; the agent retries without manual requeueing.

Useful local commands:

```text
filament-manager-agent scan
filament-manager-agent status
filament-manager-agent run-once
filament-manager-agent rollback DEPLOYMENT_UUID
```

Rollback restores the exact pre-synchronization user materials and managed plugin files captured by that deployment. Authoritative synchronization never changes Cura's machine, quality, start-G-code, or bundled installation files.

## Security and removal

Pairing codes expire after ten minutes and work once. The server stores hashes of pairing codes and agent credentials, not plaintext. Revoke an agent in the web interface before decommissioning a workstation, then run the matching uninstaller as the same non-privileged Cura desktop user:

```bash
./workstation-agent/installers/uninstall-arch.sh
```

```powershell
.\workstation-agent\installers\uninstall-windows.ps1
```

The uninstaller stops and removes the per-user service/task, installed executable or virtual environment, pairing credential, local agent state, and rollback backups. These removals are not recoverable unless separately backed up. The currently deployed Cura material files and managed visibility plugin remain installed so removing the agent does not damage Cura's working material library; remove or replace those through Cura deliberately if they are no longer wanted.
