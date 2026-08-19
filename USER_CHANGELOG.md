# User Changelog

## 0.2.5 - 08.18.2026

### Added

- Added ten automatic safe Cura recovery points per workstation installation/version, including printers, extruders, custom profiles, visibility, approved preferences, and a plugin verification list.
- Added a reviewed **Restore Cura setup** workflow that waits for Cura to close, backs up the current local state, restores the selected point, and rolls back automatically on failure.

### Changed

- Cura now automatically enables every material print setting managed by Filament Manager in the Material Settings plugin, including after a Cura recovery.
- Materials without a known manufacturer now appear in Cura's `Unknown` group.
- Active-spool changes now retry at the live polling rate instead of waiting through a long failure backoff.
- Filament cards now show vendor, material/color/display name, and filler/finish on three consistent lines. Filament editing now lists the current linked template first and includes compatible alternatives.
- Cura material descriptions now show `Filament Filler` and `Filament Finish` on separate lines, including `None` when a value is empty.
- Cura recovery keeps account sessions, passwords, API keys, private URLs, local paths, and plugin program files on the workstation; account-installed plugins are restored through Cura before the saved settings are applied.
- A reset or unexpectedly emptied Cura installation can no longer replace the last known-good recovery point.
- Paired Cura workstations must be upgraded to the 0.2.5 agent before the updated material descriptions and recovery workflow are available.

### Fixed

- Fixed print history showing recent jobs while still reporting that synchronization had never succeeded.
- Fixed filament projections remaining behind because Spoolman rejected multicolor/rainbow display metadata.
- Fixed manual material-type and color-name entry jumping to the modal close button after each letter.
- Fixed the linked-template selector being missing or stale while editing a filament.
- Fixed Cura 5.13 crashing during startup immediately after Filament Manager synchronized its managed plugin; upgrading the workstation agent now automatically replaces the affected plugin.
- Fixed there being no guided recovery path for printer, extruder, custom profile, visibility, and safe preference settings after Cura is reset to defaults.

## 0.2.4 - 08.18.2026

### Added

- Added red explanations beside each invalid template or material-profile value, including what must be corrected.
- Added automatic Cura favorites for every synchronized `Template <material type>` material.
- Added automatic backup and repair of recoverable custom Cura profiles plus safe quarantine for malformed profiles.
- Added a downloadable repository text checklist of every Cura Material Settings plugin option tracked by Filament Manager.

### Changed

- Cura's main/custom profiles remain available for print-quality and purpose settings, but filament-specific settings now come from the selected Filament Manager material.
- Filament Manager's centralized material-setting list now controls which values are removed from custom Cura profiles and enforced from materials.
- Paired Cura workstations must be upgraded to the 0.2.4 agent before this cleanup and enforcement can be installed.
- Solid, multicolor, and rainbow displays now share the same spool shape; multicolor shows its selected colors and rainbow remains visually distinct.

### Fixed

- Fixed template editing returning only `Request validation failed` without showing which values failed or why.
- Fixed Cura custom or built-in profile settings sometimes overriding the selected material's temperatures, flow, speeds, retraction, cooling, and other managed filament settings.
- Fixed synchronized template materials not appearing as favorites and malformed custom profiles continuing to produce Cura corruption warnings.
- Fixed multicolor and rainbow fills hiding the spool shape on filament and spool screens.

## 0.2.3 - 08.18.2026

### Added

- Added a recommended `Template ASA` starting point to the templates available during Cura takeover.
- Added a dedicated Cura mapping dialog that lists every reported profile beside the template it can import into, followed by a separate review step.
- Added visible highlighting around filament settings customized away from their linked template.
- Added custom color names, two- or three-color spool displays, and a rainbow spool display.
- Added complete correction and delete-or-archive actions for filaments and spools.
- Added automatic empty-spool weight calculation when a new spool is entered with its filament amount and full scale weight.

### Changed

- Filament settings now always begin with the linked template's effective values, and only changed values are retained as filament customizations.
- Retraction speed and maximum fan speed now appear once in the editor instead of being repeated under Additional Cura Material Settings.
- Cura profiles with only inherited expressions or no tracked literal overrides remain available in the one-time takeover list.
- Filament settings are grouped like Cura, changed values highlight immediately, and displayed numbers no longer show unnecessary decimal places.
- Completed, failed, and cancelled prints now reduce each exact spool by Moonraker's reported actual filament use.
- Filament color remains editable until that filament has recorded use, then locks to preserve history.

### Fixed

- Fixed the Cura takeover confirmation being rejected whenever the workstation agent checked in while the mapping dialog was open.
- Fixed the workstation agent repeatedly failing certificate verification and never reporting Cura profiles when Filament Manager uses a private CA already trusted by the workstation.
- Fixed Cura takeover reporting zero selectable profiles even though Cura contained saved profiles.
- Fixed **Back to mappings** not returning to a clear profile-and-template selection screen.
- Fixed overlapping settings appearing more than once while editing a filament profile.
- Fixed the Arch workstation agent being unable to write its Cura deployment state after installation.
- Fixed a new full-spool weight being rejected instead of calculating the empty spool weight automatically.
- Fixed incorrect new spool or filament records being difficult to correct or remove safely.

## 0.2.2 - 08.17.2026

### Added

- Added **Nozzles** for physical nozzle records, installation history, completed prints, and total filament printed.
- Added completed-print totals for every build-plate side and spool. Each distinct spool used during a completed print receives one count.
- Added **Add Side B** to each physical build plate. The side remains unavailable for selection until its exact `P#b` Klipper mesh is discovered.
- Added **Diagnostics** with all connection, synchronization, worker, and queue health; a small recent-error view; recovery validation; safe projection rebuild; and existing retry/reconciliation actions.
- Added the running app version to the sidebar and Diagnostics. Diagnostics now compares it with the newest published GitHub testing or stable release.
- Added a guided one-time Cura takeover where every discovered source has its own existing-template selector, unwanted sources can remain unmapped, and all choices are reviewed and confirmed together.
- Added saved Cura print profiles to the one-time takeover list, including their tracked literal settings and a clear count of safely omitted Cura expressions.
- Added workstation-agent uninstallers for Arch Linux and Windows.
- Added **Download log** on Diagnostics for a safe plain-text copy of the current checks, queue summary, and recent errors.

### Changed

- Operational status now lives on Diagnostics instead of being split across Dashboard, Printers, Integrations, and Cura Workstations.
- Printer nozzle details now come from installable physical nozzle records rather than editable printer text fields.
- Templates, filament profiles, calibration results, workbook imports, and known Cura edits now save directly and synchronize automatically—there are no revision, publication, or manual Cura deployment steps.
- Template changes immediately flow to every linked filament profile unless a value was explicitly customized for that filament.
- Cura expressions are skipped safely during takeover. Each selected source maps directly to one existing template; unmapped sources are ignored after backup.
- **Load Filament** now opens a live list of non-empty projected spools directly in Fluidd, even when a spool does not yet have an exact print-ready profile. Cura print starts remain restricted to exact current profiles. A spool selected in Spoolman opens a safe confirmation instead of being silently discarded.
- The sidebar now has a simple Logout button and direction-only collapse control. Light/dark theme selection moved to Settings.
- Running **Select Build Plate** without a plate now lists the current valid P-number meshes saved in Klipper.
- Workstation installers now say explicitly whether they are performing a fresh installation or an upgrade.
- Stale Cura-agent checks now show clearer workstation-service recovery guidance, and grouped Moonraker failures identify the types of errors encountered.

### Fixed

- Fixed there being no way to add the second side of an existing physical build plate.
- Fixed existing Cura source selection being difficult to find before authoritative synchronization.
- Fixed saved Cura print profiles not appearing as import choices before authoritative synchronization.
- Fixed Cura takeover lacking a clear template choice for each discovered source.
- Fixed material editing requiring draft, publish, and manual deployment actions before a change became active.
- Fixed the Target Spool error that prevented manual loading and the stale M600 selection state that reported a workflow was already active.
- Fixed manual loading incorrectly reporting that no eligible spools were available when the only missing item was profile publication.
- Fixed new build-plate meshes requiring hand-written selector buttons.
- Fixed a Klipper startup error caused by an empty Filament Manager catalog-revision value.
- Fixed the false out-of-date canonical database schema warning after upgrading to 0.2.2.
- Fixed repeating Spoolman reconciliation failures caused by fractional remaining-weight precision.
- Fixed Moonraker print-history reconciliation failing after a live-print capture error.

## 0.2.1 - 08.13.2026

### Added

- Added **Print history** with exact spool, material profile, build-plate side, G-code inspection evidence, filament changes, and print outcome scoring.
- Added optional blocking for G-code/profile mismatches under **Settings**; warning and continuing remains the recommended default.
- Added complete dimensional calibration measurements and recommendations without automatically changing Klipper configuration.
- Added visual comparison of two to four profile/template versions with recorded success rates.
- Added account lifecycle controls, plate-maintenance history and reminders, explicit unload/clear actions, mobile-friendly data cards, and a notification center for workshop conditions that need attention.

### Changed

- New and reset accounts now use a temporary password that must be changed before opening the rest of the app.
- Build-plate cleaning and mesh reminder intervals can be adjusted for each physical plate.
- Print and material state refreshes from Moonraker every five seconds by default.

### Fixed

- Fixed a print paused for preflight being able to retain the old spool in its exact starting record.
- Fixed completed live prints being duplicated by repeated Moonraker completion updates or history synchronization.
- Fixed mid-print spool-change segments not receiving their own usage totals.

## 0.2.0 - 08.13.2026

### Added

- Added **Preserve before takeover** on Cura Workstations so selected existing Cura materials can become reviewable draft templates before synchronization replaces the local library.
- Added clear draft and published states for preserved materials, with direct links to review imported templates.
- Added **Compare settings** on Material Profiles and Material Templates. It compares any profile with another profile or any saved template revision and lists only changed values.
- Added automatic Cura print spool checks. A matching loaded spool starts normally; a mismatch pauses in Fluidd so you can choose and insert the exact matching spool.
- Added a safer manual filament-change workflow that clears Spoolman after unload, preheats for the selected replacement, and activates it only after loading finishes.
- Added direct template links to filament profile details, including inherited/customized settings and a **Reset to Template** action for each override.
- Added automatic capture of edits made to existing managed Cura materials as new drafts in Filament Manager for review and publication.

### Changed

- Running either workstation-agent installer again now upgrades the existing installation while preserving pairing details, backups, and local agent state.
- Cura takeover remains unavailable until every material selected for preservation has been reviewed and published.
- Comparisons remain available across different printers and nozzle sizes, with a prominent scope warning before the difference list.
- **Set active** is now **Load spool** in Inventory. It sends the request to Fluidd and keeps showing the current physical spool until the change completes.
- Templates now appear in Cura as `Template PLA`, `Template PETG`, and the equivalent material type under the `Template` brand.
- A template update now shows its effect separately on each linked filament and creates a draft only after that filament's update is confirmed.

### Fixed

- Fixed Moonraker worker synchronization stopping when an automatic audit identifier exceeded the database limit.
- Fixed the worker showing a secondary database rollback error instead of retaining the useful original synchronization failure.
- Fixed agent upgrades conflicting with an already-running Arch Linux service or Windows scheduled task.
- Fixed a canceled or interrupted spool change being able to show the replacement spool as active before it was physically loaded.
- Fixed filament profile details not showing which template revision supplies inherited settings.

## 0.1.6 - 08.12.2026

### Added

- Added automatic active-spool, active build-plate, mesh, and printer-information updates from Moonraker.
- Added clear active-spool indicators in the spool table and selected-spool details.
- Added consistent grouped editing dialogs throughout the application, with all options visible in named sections.
- Added browser and service console diagnostics so failed requests and background synchronization errors include useful context.

### Changed

- Build Plates and Printers now synchronize automatically; manual synchronization buttons are no longer required.
- Build Plates and Printers now use roomier full-width layouts with clearly grouped summaries and editing actions.
- Filament, template, profile, spool, account, printer, plate, and calibration setup editors now share the same editing pattern.
- Cura material settings are shown in visible named groups instead of a fold-down advanced section.

### Fixed

- Fixed a spool selected in Klipper, Moonraker, or Spoolman not becoming active in Filament Manager.
- Fixed Moonraker printer and build-plate data appearing not to load because synchronization depended on nonworking manual actions.
- Fixed errors being too generic to analyze from application and browser consoles.

## 0.1.5 - 08.11.2026

### Added

- Added automatic setup and verification of the Spoolman fields Filament Manager needs for synchronization.
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

- Filament and spool changes now queue for Spoolman immediately, with a complete one-minute safety synchronization that also rebuilds missing Spoolman inventory.
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

- Fixed existing filaments and spools never appearing in Spoolman because its required custom fields and value format were not being prepared correctly.
- Fixed failed or interrupted Spoolman work remaining stuck instead of recovering automatically after redeployment.
- Fixed routine metadata synchronization being able to overwrite printer-recorded filament usage before it was imported.
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
