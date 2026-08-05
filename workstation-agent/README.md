# Filament Manager Workstation Agent

The workstation agent is the outbound-only bridge between Filament Manager and Cura. Install it under the same desktop account that runs Cura on every Arch Linux and Windows 11 workstation.

It discovers Cura user-data versions and machine instances, waits until Cura closes, then installs matched material and quality-change profiles using an automatic backup and atomic file replacement. It has no listening port and its credential can be revoked from Filament Manager.

See [../docs/CURA_WORKSTATION_AGENT.md](../docs/CURA_WORKSTATION_AGENT.md) for installation, pairing, service operation, rollback, and troubleshooting.
