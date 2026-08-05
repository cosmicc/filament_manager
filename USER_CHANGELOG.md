# User Changelog

## 0.1.0 - 08.05.2026

### Added

- A new Filament Manager dashboard, spool inventory, manual weighing flow, build-plate views, and calibration wizard.
- Light and dark themes and mobile-friendly weighing near the printer.
- Administrator, Operator, and Viewer access levels.
- Spool labels, material profiles, printer controls, integration status, and an activity history.
- Automated Cura profile delivery to paired Arch Linux and Windows 11 workstations, including material, quality, printer/nozzle settings, guarded pressure advance, backup, and rollback.
- A Cura workstations page with secure pairing, connection status, detected Cura machines, deployment progress, and agent revocation.

### Changed

- The original workbook is now an import source; ongoing inventory updates happen in Filament Manager.
- Spoolman remains available to Fluidd while Filament Manager safely reconciles printer-recorded usage.
- Published profiles can now be deployed to every active Cura workstation with one action; manual Cura JSON download remains available.

### Fixed

- Preserved the second historical `P11` spool as `P11-S` so every physical spool has a unique code.
- Cura profile changes wait automatically until Cura closes and restore their backup if a write fails.
