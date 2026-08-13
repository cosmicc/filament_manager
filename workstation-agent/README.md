# Filament Manager Workstation Agent

The workstation agent is the outbound-only bridge between Filament Manager and Cura. Install it under the same desktop account that runs Cura on every Arch Linux and Windows 11 workstation.

It discovers Cura user-data versions, machine instances, sanitized existing material settings, known managed-material edits, and desired-library drift. It waits until Cura closes, then backs up the affected user files and atomically installs Filament Manager's complete published `Template <material type>` and product material library plus its bundled-material visibility plugin. Existing user materials require explicit Administrator takeover; clean installs synchronize automatically. Changes to approved settings on known managed entries return to Filament Manager as reviewable drafts, while new or copied Cura materials are never imported. It never changes quality profiles, machine settings, start G-code, or Cura installation files, has no listening port, and its credential can be revoked from Filament Manager.

See [../docs/CURA_WORKSTATION_AGENT.md](../docs/CURA_WORKSTATION_AGENT.md) for installation, pairing, service operation, rollback, and troubleshooting.
