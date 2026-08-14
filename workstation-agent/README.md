# Filament Manager Workstation Agent

The workstation agent is the outbound-only bridge between Filament Manager and Cura. Install it under the same desktop account that runs Cura on every Arch Linux and Windows 11 workstation.

It discovers Cura user-data versions, machine instances, sanitized existing material settings, known managed-material edits, and desired-library drift. It waits until Cura closes, then backs up the affected user files and atomically installs Filament Manager's complete published `Template <material type>` and product material library plus its bundled-material visibility plugin. Existing user materials require explicit Administrator takeover; clean installs synchronize automatically. Changes to approved settings on known managed entries return to Filament Manager as reviewable drafts, while new or copied Cura materials are never imported. It never changes quality profiles, machine settings, start G-code, or Cura installation files, has no listening port, and its credential can be revoked from Filament Manager.

The installers explicitly report fresh installation versus in-place upgrade. Matching Arch Linux and Windows uninstallers remove the per-user agent service/task and private agent files while leaving Cura's currently deployed managed library usable.

See [../docs/CURA_WORKSTATION_AGENT.md](../docs/CURA_WORKSTATION_AGENT.md) for installation, pairing, service operation, rollback, removal, and troubleshooting.
