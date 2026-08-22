# Cura Workstation Agent

## What it automates

Each Arch Linux or Windows 11 workstation runs one agent under the same user account as Cura. The agent automatically:

- discovers standard Cura, Flatpak, and Snap user-data locations on Arch Linux and `%APPDATA%\cura` on Windows;
- reports version, machine metadata, verified desired-library checksum, unmanaged import-source counts, and sanitized approved settings from existing materials and saved print profiles, never absolute workstation paths;
- receives the current `Template <material type>` entries and resolved product profiles as one desired-state library through an outbound HTTPS poll;
- reports approved setting edits to known managed material GUIDs so the server can save the corresponding current settings directly without accepting new Cura-created materials;
- waits while Cura is open;
- matches the Filament Manager printer and nozzle to one Cura machine instance;
- installs official-format `.xml.fdm_material` files plus the managed plugin that hides bundled materials, favorites every Template, merges product purchase-cost rates for Cura print estimates, and enforces selected-material values over Cura's higher profile layers;
- backs up every added, replaced, removed, repaired, or quarantined user material, managed-plugin, and affected custom-profile file, writes same-filesystem temporary files, and atomically replaces targets;
- removes current and cleanup-only retired centrally managed material keys from custom Cura profiles, repairs recoverable duplicate sections, and quarantines malformed bounded profiles so Cura no longer loads them;
- records a complete-library checksum so repeated synchronizations are idempotent and heartbeat drift is repaired;
- retires older failed desired-library states after the current full library installs successfully, without deleting their history;
- restores the backup automatically if any write fails;
- captures a sanitized exact-version Cura recovery point whenever Cura is closed and the installation still contains a printer; and
- applies an Administrator-confirmed recovery only to the same workstation/version after making a separate local rollback archive.

Install and enable the Cura **Material Settings** and **Klipper Settings** plugins. After Cura finishes initialization, Filament Manager's managed plugin replaces the Material Settings plugin's enabled-setting list with the 55 non-metadata keys from the complete central catalog in `docs/CURA_MATERIAL_PRINT_SETTINGS.txt`; this is also reapplied after a recovery or manual preference drift. It verifies those keys against the active Cura definitions and writes an atomic value-free receipt. The outbound agent binds that receipt to the deployed manifest and reports expected/exposed counts, missing/extra keys, required-plugin versions/readiness, and the last verification time to Cura Workstations and Diagnostics. Material Type and Material Brand remain XML metadata, so the complete document contains 57 entries while the plugin selection contains 55. For each product whose current usable priced spools have one currency, the plugin writes a normalized 1,000 g cost basis equal to the net-weighted purchase cost per gram. Cura has no currency field, so mixed-currency products omit the estimate. Unrelated Cura cost preferences remain untouched. Filament Manager stores pressure advance as `klipper_pressure_advance_factor` and smooth time as the Klipper plugin's material settings. Cura main/custom profiles remain local and are not synchronized. The agent never creates a quality profile, changes bundled profiles, patches machine start G-code, or alters unrelated custom-profile settings.

For physical-spool preflight, the operator must make the one-time Cura machine start-G-code change documented in [INSTALL.md](../INSTALL.md). The agent supplies each managed material's stable GUID but intentionally preserves the complete machine start/end G-code. Select a product material, not a `Template <material type>` entry, when sending a print that must resolve to physical inventory.

Existing Cura material files are parsed with a hardened XML parser. Saved print profiles under Cura's `quality_changes` directory are read without modification through a non-interpolating bounded parser; matching global and first-extruder layers are merged, explicit values from the extruder layer win, and Cura expressions are omitted rather than evaluated. Both paths report only the approved settings tracked by Filament Manager. Unsupported settings, additional extruders, file paths, machine settings, and start G-code are discarded.

On **Templates**, choose **Import from Cura**, or open **Cura workstations** directly. While the workstation says **Awaiting one-time takeover**, select **Map Cura profiles** to open the mapping dialog. Every reported material and saved print profile appears beside a Filament Manager template selector, including named profiles whose tracked values are all inherited expressions. Choose the existing template each source should update, or leave it as **Do not import**. Each source and template may be used once. Continue to the separate review, verify all mappings and the ignored count together, then select **Complete takeover** once. **Back to mappings** always returns to the selectors. Filament Manager applies the mapped literal settings, updates linked profiles through normal inheritance, records provenance, enables management, and queues synchronization atomically. Unmapped user sources are backed up and then replaced by the managed library. Bundled files in Cura's installation remain untouched; the managed plugin hides them in material selectors.

After management is enabled, an edit to approved settings in an existing Filament Manager material is detected by its deterministic GUID and content checksum. The server saves that known template/profile directly and idempotently, preserves explicit filament customizations during template inheritance, and queues the current library for synchronization. Product materials use their manufacturer as Cura brand and use `Unknown` when no manufacturer is recorded. Pre-takeover print-profile discovery does not continue as a source of canonical additions after management begins. New or copied Cura materials, changed identity metadata, unknown GUIDs, machine configuration, quality-profile changes, and start/end G-code are never imported. Add all new templates and filament products in Filament Manager.

Cura's sidebar, custom profile, and built-in quality layers normally override material values. The managed plugin uses the central Filament Manager catalog to remove those keys from the active custom layer and mirror the selected material's explicit values into Cura's supported top user layer. Main profiles therefore remain useful for non-material choices, while temperatures, flow, filament-dependent speed/retraction/cooling, dimensional compensation, and Klipper material values come from the selected managed material. If Cura is closed and a saved custom profile reintroduces a managed key, checksum drift queues another backed-up cleanup.

## Server requirement

Use an HTTPS Filament Manager public URL. Plain HTTP pairing is accepted only for an explicit loopback development installation. The agent follows no HTTP redirects and validates the normal operating-system certificate trust store, including private CA roots installed by the workstation operator. Standard `SSL_CERT_FILE` and `SSL_CERT_DIR` overrides remain available when a managed service needs an explicit trust bundle; certificate verification cannot be disabled.

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

The hardened user unit writes only to supported Cura and agent data locations. If Cura uses a nonstandard location, add it to `ReadWritePaths` and set `FILAMENT_MANAGER_CURA_ROOTS` in a systemd user-service override. Nozzle changes read existing variants from the normal Cura user-data and application-resource locations. For a nonstandard Cura package, set `FILAMENT_MANAGER_CURA_RESOURCE_ROOTS` to one or more Cura resource directories (the parent of `variants`, separated by the platform path separator); this override is read-only and does not relax the exact printer-and-diameter match.

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

Before takeover, open **Cura workstations** and wait for the agent to report unmanaged material import sources and user-saved custom print profiles. After takeover, the page reports the synchronized managed-material count instead; zero user-saved custom print profiles is normal when Cura has no custom quality profiles. If an expected source count is unexpectedly zero, upgrade or restart the agent, keep Cura closed, and wait for the next check-in. Version 0.3.3 continues to use Cura deployment schema 3, so every paired workstation must run the 0.3.3 agent before using current recovery, nozzle, and reporting behavior. Select **Map Cura profiles**, map any source you want to keep to an existing template, and leave all others as **Do not import**. A recommended `Template ASA` is seeded for the configured printer/nozzle when no ASA template already exists. Use **Review takeover**, verify the mappings and ignored count, then select **Complete takeover**. Routine agent check-ins do not invalidate the dialog; an actual source-content change requires a fresh review. A genuinely clean installation can complete with zero mappings. Cura shows and favorites bases as `Template PLA`, `Template PETG`, and so on under brand `Template`; manufacturer-less products appear under `Unknown`. Every generated material description lists its filler and finish on separate labeled lines, using `None` when a field is empty. Later template or product saves queue the complete library automatically. Close Cura when synchronization is pending; the agent retries without manual requeueing.

Useful local commands:

```text
filament-manager-agent scan
filament-manager-agent status
filament-manager-agent run-once
filament-manager-agent rollback DEPLOYMENT_UUID
```

Rollback restores the exact pre-synchronization user materials, managed plugin files, and affected user quality-change profiles captured by that deployment. Corrupt originals are also copied to the agent's `quarantine` data directory under the deployment identity before removal from Cura. Authoritative synchronization never changes Cura's machine, bundled quality, unrelated custom-profile settings, start-G-code, or installation files.

## Full Cura configuration recovery

This recovery protects the workstation-owned Cura configuration that ordinary material synchronization intentionally leaves alone. Whenever Cura is fully closed, the agent captures the complete bounded non-sensitive contents of allowlisted printer, extruder, and definition-change documents—including opaque machine start/end G-code and safe printer/extruder options—plus user definitions and variants, intent and custom quality state, visibility settings, safe Cura preferences, and the installed plugin names, versions, and enabled state. The application can also queue an immediate named backup, and each retained point can be named, described, or individually deleted with confirmation. Cura Workstations shows each recent named request as pending, capturing, saved, or failed with a sanitized actionable reason. Filament Manager retains the ten newest points for each discovered installation and Cura version; automatic captures remain content-deduplicated while explicitly named captures may preserve the same configuration more than once. Deleting an automatic point suppresses that exact version/content checksum so it does not immediately reappear; changed settings and explicit named captures remain eligible. If the agent sees no printer, capture remains blocked. A large deletion blocks automatic capture and preserves the last known-good point, while an explicit named request may save the current reset state as a separate point.

Account sessions, passwords, tokens, API keys, private connection URLs, local paths, and plugin executable files are removed or excluded before upload. Safe Cura2Moonraker behavior choices such as upload/start behavior, output format, transformations, camera orientation, and power-device selection are retained. Restore merges those choices into the current local plugin instance while preserving its current Moonraker URL and API key. Browser users can review metadata and plugin inventory, never the stored file contents. Plugin code still comes from Cura account synchronization.

To recover from Cura defaults:

1. Install or reset the same Cura version.
2. Open Cura, sign in to the Cura account, and wait for account-managed plugins to install.
3. Close Cura completely.
4. In **Cura Workstations**, select **Restore Cura setup**, choose the matching recovery point, review it, and confirm.
5. Leave Cura closed until the recovery status returns to **Ready**.
6. Re-enter excluded Moonraker, OctoPrint, or other connection credentials only if the reset Cura installation does not already contain them.

Installing a different physical nozzle queues a closed-Cura machine/extruder update for every managed workstation. The agent matches one exact enabled position-zero extruder, backs up its machine, extruder, and definition-change documents, writes the current diameter to that extruder's existing `machine_nozzle_size` setting, and selects one exact existing nozzle variant when available. It never manufactures a variant or settings container. A completed Cura recovery automatically queues the same alignment again before the material library so restored settings cannot supersede the app's canonical nozzle.

The agent first archives every allowlisted target it may replace, writes the selected configuration atomically, removes stale allowlisted files, merges safe preferences into the current `cura.cfg` without replacing excluded login/connection data, and rolls back automatically if any write fails. Normal authoritative synchronization then restores Filament Manager's current material library. The restore is never transferred to another agent identity or a different Cura version.

## Cura startup recovery

If Cura crashes immediately after synchronization and `cura.log` reports an active-machine startup failure involving `_i18n_catalog`, stop the workstation agent before retrying Cura. Close Cura and its crash dialog, then move the `FilamentManagerVisibility` directory outside that Cura version's `plugins` directory; moving it preserves a recoverable copy and leaves all material files untouched. Start Cura to confirm recovery, upgrade to an agent containing the startup-order fix, close Cura, and restart the agent so it can reinstall the corrected plugin. Do not restart an older agent while the plugin is moved because desired-state repair will restore that older plugin.

For the standard Arch service:

```bash
systemctl --user stop filament-manager-agent.service
mkdir -p ~/FilamentManager-Cura-Recovery
mv ~/.local/share/cura/5.13/plugins/FilamentManagerVisibility ~/FilamentManager-Cura-Recovery/
```

Replace `5.13` if the affected Cura user-data version differs. On Windows, stop the **Filament Manager Cura Agent** scheduled task and move the same plugin directory outside `%APPDATA%\cura\<version>\plugins` before starting Cura.

## Security and removal

Pairing codes expire after ten minutes and work once. The server stores hashes of pairing codes and agent credentials, not plaintext. Revoke an agent in the web interface before decommissioning a workstation, then run the matching uninstaller as the same non-privileged Cura desktop user:

```bash
./workstation-agent/installers/uninstall-arch.sh
```

```powershell
.\workstation-agent\installers\uninstall-windows.ps1
```

The uninstaller stops and removes the per-user service/task, installed executable or virtual environment, pairing credential, local state, deployment rollback backups, and pre-recovery archives. These removals are not recoverable unless separately backed up. The currently deployed Cura material files and managed visibility plugin remain installed so removing the agent does not damage Cura's working material library; remove or replace those through Cura deliberately if they are no longer wanted.
