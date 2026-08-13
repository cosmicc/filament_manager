# Cura Workstation Agent

## What it automates

Each Arch Linux or Windows 11 workstation runs one agent under the same user account as Cura. The agent automatically:

- discovers standard Cura, Flatpak, and Snap user-data locations on Arch Linux and `%APPDATA%\cura` on Windows;
- reports version, machine metadata, verified desired-library checksum, unmanaged user-material count, and sanitized approved settings from existing materials, never absolute workstation paths;
- receives the latest published `Template <material type>` entries and resolved product profiles as one desired-state library through an outbound HTTPS poll;
- reports approved setting edits to known managed material GUIDs so the server can create reviewable draft revisions without accepting new Cura-created materials;
- waits while Cura is open;
- matches the Filament Manager printer and nozzle to one Cura machine instance;
- installs official-format `.xml.fdm_material` files plus the managed visibility plugin that hides bundled materials from Cura's selectors;
- backs up every added, replaced, or removed user material and managed-plugin file, writes same-filesystem temporary files, and atomically replaces targets;
- records a complete-library checksum so repeated deployments are idempotent and heartbeat drift is repaired; and
- restores the backup automatically if any write fails.

Install and enable the Cura **Material Settings** and **Klipper Settings** plugins. Filament Manager stores pressure advance as `klipper_pressure_advance_factor` and smooth time as the Klipper plugin's material settings. The agent never patches machine start G-code and never creates or changes quality profiles.

For physical-spool preflight, the operator must make the one-time Cura machine start-G-code change documented in [INSTALL.md](../INSTALL.md). The agent supplies each managed material's stable GUID but intentionally preserves the complete machine start/end G-code. Select a product material, not a `Template <material type>` entry, when sending a print that must resolve to physical inventory.

Existing Cura material files are parsed with a hardened XML parser. Only the approved Material Settings keys are reported; unsupported settings, file paths, and machine start G-code are discarded. On **Cura workstations**, import each material you want to preserve as a draft template, review it on **Templates**, and publish it before enabling authoritative management. Filament Manager records the source workstation and material identifier and prevents duplicate imports. Once any material is selected for preservation, takeover remains blocked until all selected imports are active and published. Enabling management on a workstation with existing user material files still requires an explicit Administrator confirmation because unselected files will be backed up and replaced by Filament Manager's complete library. Bundled files in Cura's installation remain untouched; the managed plugin hides them in material selectors.

After management is enabled, an edit to approved settings in an existing Filament Manager material is detected by its deterministic GUID and content checksum. The server creates one idempotent draft template/profile revision for review and then restores the published desired library. New or copied Cura materials, changed identity metadata, unknown GUIDs, machine configuration, quality settings, and start/end G-code are never imported. Add all new templates and filament products in Filament Manager.

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
standalone binary.

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
previous executable.

Create a pairing code in **Cura workstations**, run the command printed by the installer, then start the per-user logon task:

```powershell
Start-ScheduledTask -TaskName 'Filament Manager Cura Agent'
```

## Use

Create and publish material templates first; Cura shows them as `Template PLA`, `Template PETG`, and so on under brand `Template`. Add filament products from those bases, tune and publish each resolved product profile, then open **Cura workstations**. For an installation with existing user materials, use **Import as draft** for each material you want to preserve, review and publish those templates, then choose **Manage and synchronize Cura** and accept the replacement warning. A clean Cura installation is managed automatically. Publishing later template or product revisions queues the complete library automatically. Close Cura when synchronization is pending; the agent retries without manual requeueing.

Useful local commands:

```text
filament-manager-agent scan
filament-manager-agent status
filament-manager-agent run-once
filament-manager-agent rollback DEPLOYMENT_UUID
```

Rollback restores the exact pre-synchronization user materials and managed plugin files captured by that deployment. Authoritative synchronization never changes Cura's machine, quality, start-G-code, or bundled installation files.

## Security and removal

Pairing codes expire after ten minutes and work once. The server stores hashes of pairing codes and agent credentials, not plaintext. Revoke an agent in the web interface before decommissioning a workstation, then remove its scheduled task or systemd user unit and its private configuration directory.
