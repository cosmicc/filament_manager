# User Changelog

## 0.1.5 - 08.11.2026

### Added

- Added Side A and Side B tracking for physical build plates. `P4` is Side A and `P4b` is Side B of the same P4 plate.
- Added plate descriptions and independent surface material, smooth/textured finish, notes, mesh availability, mesh check time, and mesh calibration time for each side.
- Added a **Synchronize with Moonraker** action that imports exact P-number side meshes, including later plates such as P6 and optional B sides such as P6b.
- Added import of existing Cura materials from paired workstations into new draft material profiles.
- Added reusable Generic PLA, PETG, ASA, PLA+, TPU, PCTPE, Nylon 645, and other material templates, with saved revisions for each printer and nozzle.
- Added interface actions to create filament products from templates and add physical spools without using Spoolman.
- Added automatic database updates whenever a newer Filament Manager container starts.
- Added automatic full-library Cura synchronization, backup and rollback, drift repair, and an option to hide Cura's bundled materials.
- Added existing Spoolman bucket import plus a free-text **Edit location** action for each spool.
- Added real filament color samples. A selected sample is remembered by color name and automatically used by every matching existing or future filament.
- Added a filament details page for editing product information and every Cura material setting saved for that filament.
- Added complete build-plate editors for physical properties, condition, supported materials, temperature limit, each side, and notes.
- Added printer cards with editable hardware details and a **Pull from Moonraker** action for Klipper/Moonraker versions, kinematics, nozzle size, hostname, and build volume.
- Added Size and Hole Calibration after Retraction. Enter the model and measured X, Y, and hole sizes to calculate Cura Horizontal Expansion and Hole Horizontal Expansion.

### Changed

- Kept P1 through P5 as the starter physical plates while allowing later numbered plates and B sides to be added from Moonraker.
- The currently loaded matching Moonraker mesh now records both the active physical plate and which side is facing up.
- Cura deployments now install material settings only. The Cura Material Settings plugin exposes them for editing, and the Cura Klipper Settings plugin applies pressure advance and smooth time.
- Each new filament product starts from a published generic template but receives its own draft settings that can be tuned without changing other products.
- Filament Manager becomes the authoritative Cura material library after workstation management is enabled. Existing user materials require a clear Administrator confirmation before replacement.
- Filament Manager becomes authoritative for a spool's bucket after importing, editing, or clearing it and keeps Spoolman synchronized.
- Usernames may now be as short as two characters, and new passwords may be 10 or more characters.
- Calibration now has seven steps, and its published result keeps every unchanged setting from the filament's starting profile.
- Editing a material profile saves a new draft version so existing published Cura settings remain recoverable.

### Fixed

- Fixed a Klipper startup error caused by the initial build-plate macro value.
- Fixed later plates such as P6 and P10 being rejected or ordered incorrectly.
- Missing meshes no longer remove plate records or their physical or side-specific details.
- Database upgrades no longer need a separate migration command before every deployment.
- Cura workstations now restore the complete published library when local material files drift.
- The supplied Klipper macro now uses an explicit quoted initial plate value, and troubleshooting identifies older included copies.
- Fixed matching named colors showing different or missing samples across filament, spool, label, and dashboard views.
- Fixed product-specific Cura settings and full plate/printer details not having complete in-app editing screens.
- Fixed calibration publication losing template-derived settings that were not part of a calibration result.

## 0.1.4 - 08.11.2026

### Added

- Added a Printers page button for Administrators to create the configured printer and P1-P5 build plates from the current deployment settings.
- Added automatic first-run setup of the configured printer and P1-P5 build plates during browser workbook import.

### Changed

- Simplified workbook commit so Administrators no longer need to run the separate seed command first.

### Fixed

- Fixed the Printers page setup message pointing Docker installs at a YAML file instead of deployment variables.
- Fixed workbook commit stopping with `seed the configured printer before importing profiles` on a fresh installation.

## 0.1.3 - 08.11.2026

### Added

- Added a Settings workbook import panel so Administrators can upload the master `.xlsx`, validate it, and commit it from the browser.
- Added recent workbook import history with validation totals and row-level errors or warnings.

### Changed

- Simplified first inventory setup by making the browser upload flow the primary workbook import path.

### Fixed

- Fixed workbook uploads failing because the browser request could be labeled as JSON instead of multipart form data.

## 0.1.2 - 08.11.2026

### Added

- Added deployment checks that prevent web-only health monitoring from being applied to background services.

### Changed

- Updated container health monitoring to use the configured Filament Manager hostname securely.

### Fixed

- Fixed web and worker containers eventually exiting even though the application and background processing had started successfully.

## 0.1.1 - 08.11.2026

### Added

- Added a single production stack that starts Filament Manager, its background worker, and Spoolman together while using an existing remote PostgreSQL server.
- Added ready-to-pull AMD64 and ARM64 Filament Manager container images for easier first-time deployment.

### Changed

- Simplified production installation and documented the complete remote database and first-user setup.
- Changed the current Docker setup to use stack environment variables instead of requiring Docker secret objects.
- Moved the Filament Manager URL, Spoolman URL, and one supported Moonraker printer's settings into deployment variables so no separate application config object is required.
- Updated the central database settings for the dedicated non-SSL network and the `filament_user` account.

### Fixed

- Clarified how deployment variables must be loaded before a command-line Swarm deployment.

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
