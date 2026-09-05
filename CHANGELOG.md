# Changelog

## 0.7.1 - 09.05.2026

Testing release.

### Added

- Added optional template-only filament drying temperature in the temperature section, inherited read-only in filament and spool details. It is never sent as a Cura setting or heater command. Migration `e3f4a5b6c789` adds its nullable resolved-profile cache; existing values remain unset.
- Added remembered **Location** dropdowns to both spool forms, with **Unassigned**, existing/archived location choices, and a final **New Location** dialog that preserves unsaved spool values.
- Added **New Color**, **New Manufacturer**, **New Filler**, and **New Finish** selectors with saved choices, nested creation dialogs, and automatic selection without losing the parent form draft.
- Added **Change template** on filament print-settings cards. Preserve custom values, inherit the new defaults, and correct the filament material type across compatible scopes without rewriting retained profiles or print history.
- Added **Locations** below Spools, grouping existing canonical location labels with counts, remaining filament, an Unassigned group, optional archived inventory, and paginated spool selection that opens the normal spool detail/actions.
- Added template-derived **All**/material-type dropdowns beside search on Filaments and Spools.
- Added read-only current total spool weight, calculated from remaining filament plus current empty-spool tare.
- Added manufacturer-specific saved tare suggestions, including archived spools, ranked by frequency with original filament capacity. Suggestions require explicit selection; unknown manufacturers are never pooled.
- Added live tare-edit previews and a used/unused choice during spool creation so only unused spools infer tare from purchase weight.
- Documented direct dependency review, combined Node 22 validation, and verified merged-branch cleanup. CodeRabbit is not part of the project workflow.

### Changed

- Migration `d2e3f4a5b678` seeds a location-label catalog without changing spool assignments or historical records. Newly named locations remain available even when unused; moving the last spool does not discard its old choice.
- Color names are selected, not entered freely in the dropdown. Manufacturer replaces Vendor in filament forms/details. Filler defaults to **None** and Finish to **Standard**; these remain omitted from derived names.
- Migration `c1d2e3f4a567` seeds durable filler/finish choices from all existing filaments, fills only blank canonical modifiers, audits each correction, and queues Spoolman metadata repair. Existing populated values and historical snapshots are unchanged.
- Renamed the spool editor's **Bucket or location** field to **Location**, retaining **Bucket 12** as its example.
- Recalculate measured spool balances whenever spool settings are saved using the last accepted gross observation, current tare, and subsequent signed usage/manual corrections. Preserve purchase-based estimates when no physical observation exists; retain original weigh-ins and append tare-adjustment history instead of rewriting measurements. No schema migration or additional Moonraker polling is required.
- Applied the approved release-retention policy: retain the newest five published releases and every Git tag; verified and backed up the 28 older releases and 84 attached packages/checksum files before removing their GitHub release entries. See `docs/RELEASE_RETENTION.md`.
- Updated React Query and Query Core from 5.101.4 to 5.102.8, the React Refresh ESLint plugin from 0.5.4 to 0.5.5, and Node type definitions from 24.13.3 to 26.4.0 after compatibility and combined frontend validation. The build runtime remains Node 22.
- Kept the ESLint 10 and `@eslint/js` 10 updates deferred because their peer requirements conflict with the current lint toolchain. Existing release tags remain unchanged; application and workstation package version surfaces are prepared locally for 0.7.1.

### Fixed

- Added full-scale-weight save regression coverage: manufacturer data and response validation finish before commit, with atomic rollback of the spool, initial measurement, audit, and projections on response failure. Successful saves no longer turn into save errors when subsequent browser refreshes fail.
- Nested creation dialogs isolate focus, Escape, and form submission so the parent draft is not submitted or dismissed accidentally.
- Added regression coverage for case-insensitive color/filler/finish search in both filament and spool catalogs.
- Fixed stale remaining filament after a tare edit, preserving consumption since the last weigh-in and preventing repeated saves from duplicating corrections. Explicit net corrections and tare adjustments queue supported Spoolman remaining-weight updates and inventory publication.
- Prevent old Spoolman balances from being reimported as consumption while an explicit weight correction is still awaiting delivery. Terminal print accounting respects tare corrections after print capture without rewriting immutable snapshots.
- Fixed manufacturer-linked spool creation/filament reassignment attempting an asynchronous vendor lookup during response serialization; load the vendor explicitly and validate spool responses before committing.
- Preserve stored weight precision when an unrelated spool field is saved; rounded display values are not silently submitted as weight changes.
- Included the React Refresh lint-plugin fix for uppercase constant re-exports incorrectly treated as React components.
- Completed the material-comparison and new-filament browser fixtures for existing profile/template reads so isolated runs cannot leak those requests to an unavailable backend.

## 0.7.0 - 09.04.2026

### Added

- Added an immutable, versioned print-settings snapshot containing the complete resolved Filament Manager profile, its linked template at print time, semantic template differences, and every safely bounded Cura `SETTING_3` global and per-extruder value embedded in the G-code.
- Added an **Advanced print settings** Print History overlay that exposes captured managed, template, difference, global Cura, and per-extruder Cura values while preserving formulas as unevaluated text.
- Added a post-creation prompt that can open the new-spool form with the newly created filament already selected.
- Added **Create spool from filament** to active filament details with automatic filament preselection.

### Changed

- Changed Print History polling responses to omit large settings archives and retrieve one only through the authenticated detail request when its print is opened.
- Filament and spool searches now match filler and finish, and every app, Fluidd, Spoolman, and managed Cura product identity includes each specified filler and finish while omitting blank and `None`-style values.
- Changed profile customization ownership to semantic comparison, so numerically equal representations are inherited and stale equal-to-template values no longer inflate custom counts.
- Removed the editable filament **Display name** field. Live names derive from Type · Color · Filler · Finish, omit `Standard` as well as absent modifiers, and leave legacy stored identities and historical snapshots intact.
- Aligned Spoolman filament names and spool descriptions with the derived application identity; Spoolman's 64-character filament-name limit is respected and the full name and spool code are retained in comments alongside existing notes.
- Changed every server, browser, workstation-agent, and Klipper macro version surface to 0.7.0 and incremented the workstation renderer revision to 20 for automatically derived managed Cura labels.

### Fixed

- Fixed missing Spoolman filament price, empty-spool weight, extruder temperature, and bed temperature. Defaults use currency-safe weighted purchase cost scaled to nominal filament weight, the newest non-archived spool's tare, and the configured printer's current installed-nozzle profile; physical spools retain their own price and tare. Missing or ambiguous defaults clear stale remote values.
- Profile saves, spool measurements/deletion, and physical nozzle changes now queue refreshed Spoolman defaults. Full reconciliation batch-loads the defaults from PostgreSQL without extra Moonraker reads or overwriting printer-recorded use.
- Fixed initial build-plate temperatures that matched their template still appearing custom after revert and save.
- Fixed profiles reporting a custom-setting count when every visible setting was inherited.

## 0.6.7 - 08.31.2026

### Added

- Added regression coverage for stale interrupted-print backup deferral, storage-permission failure handling, combined Moonraker live capture, active-print synchronization deferral, navigation order, and sidebar Logout removal.

### Changed

- Moved Print History directly below Printers in the application navigation, renamed **Create pairing code** to **Add Cura workstation**, and removed Logout from the persistent sidebar.
- Restyled the database-backup schedule into a clearly grouped enable, interval, retention, and save surface, and now retain the newest bounded failure guidance in Diagnostics.
- Changed the Dashboard, Moonraker state, and live print intervals from five to ten seconds. Live print and preflight state now use one combined Moonraker object query, while active-spool, bed-mesh, catalog, printer-information, and complete-history reads defer during active prints.
- Changed every server, browser, workstation-agent, and Klipper macro version surface to 0.6.7; Cura renderer revision 18 remains current because no generated workstation files changed.

### Fixed

- Fixed manual and automatic backups remaining blocked indefinitely when an MCU shutdown left a stale canonical print marked in progress; stale state now requires a minimal terminal-state confirmation from Moonraker and fails closed when the printer cannot be checked.
- Fixed application-data-volume permission and storage failures replacing the useful backup error or causing an overly frequent scheduler retry; failures remain bounded, path-free, and visible in Diagnostics.
- Reduced avoidable printer-host work during motion to lower Filament Manager's contribution to host scheduling pressure behind Klipper `Timer too close` shutdowns.

## 0.6.6 - 08.30.2026

### Added

- Added four coordinated dark GUI themes: Deep Ocean, Carbon Lime, Ember Red, and Arctic Slate.
- Added one-click creation of the next numbered physical build plate with an initial Side A record, plus explicit missing-Klipper-heatmap warnings.
- Added printer filters to Print History and Nozzles, with **All printers** as the Print History default.
- Added a one-day, seven-day, or thirty-day Recent errors cutoff on Diagnostics, defaulting to one day and applying to the sanitized log download.

### Changed

- Changed browser sessions to a thirty-day absolute lifetime with a rolling seven-day idle window for active pages.
- Changed the printing Dashboard layout so the progress/state area receives more space and the three temperature cards become compact while a print is active.
- Changed Print History rows and mobile cards to use subtle green, yellow, or red outcome backgrounds for completed, cancelled, or failed prints while retaining text status.
- Changed Filaments and Print settings headers so the Catalog/Print settings selector sits immediately before the primary action.
- Removed the redundant Integrations browser page and navigation entry; live operational status remains consolidated in Diagnostics and supported backend integration APIs remain available.
- Changed every server, browser, workstation-agent, and Klipper macro version surface to 0.6.6; Cura renderer revision 18 remains current because no generated workstation files changed.

### Fixed

- Fixed AMD64/ARM64 image publication timing out while running the architecture-neutral frontend package installation through ARM64 emulation; the frontend now builds once on the native BuildKit platform and is copied into both target images.
- Fixed automatic and manual PostgreSQL backups against newer database servers by installing PostgreSQL client 18, returning bounded actionable failure categories, deferring backup work during active prints, and applying a fifteen-minute-to-six-hour exponential retry delay after automatic failures.
- Fixed an unbounded Klipper delayed-G-code resume retry that could continue every quarter second when a managed virtual-SD hold never reached its expected release state; retries now stop after thirty seconds and show explicit Retry and Cancel actions.
- Fixed unnecessary full Moonraker history downloads every five seconds during active printing; live exact-state capture remains at five seconds and full history reconciliation resumes immediately after the print reaches a terminal state.

## 0.6.5 - 08.29.2026

### Added

- Added the active Filament Manager Klipper macro version to `FILAMENT_MANAGER_SPOOL_STATE` output and regression coverage for direct virtual-SD hold cancellation.

### Changed

- Changed every server, browser, workstation-agent, and Klipper macro version surface to 0.6.5; Cura renderer revision 18 remains current because no generated workstation files changed.

### Fixed

- Fixed **Cancel Print** failing to unload and reset a Cura file held directly with virtual-SD `M25`, which could leave Klipper reporting an active print and Fluidd disabling printer power controls after cancellation or restart.

## 0.6.4 - 08.29.2026

### Added

- Added integration coverage for a G-code inspection captured before Klipper's blocking gate becomes visible and for a transient failure while acknowledging the persisted decision.

### Changed

- Changed blocking G-code gate acknowledgements to use the persisted inspection evidence as a fail-closed decision and retry it on every current-print pass while Klipper still reports the inspection phase.
- Changed every server, browser, and workstation-agent version surface to 0.6.4; Cura renderer revision 18 remains current because no generated workstation files changed.

### Fixed

- Fixed Fluidd remaining indefinitely on **Inspecting G-code** when concurrent Moonraker state reads straddled the start gate or the first post-inspection acknowledgement failed after the canonical print record committed.

## 0.6.3 - 08.28.2026

### Added

- Added a retryable Print History unavailable state that reports bounded request failures instead of presenting them as an empty canonical history.

### Changed

- Changed the Dashboard hierarchy so the full-width printer status card appears first, followed immediately by the three inventory value cards, and removed the redundant title description.
- Changed managed Cura product labels to omit filler text when the value is missing, blank, `None`, or `No filler`, while retaining meaningful fillers exactly once.
- Changed every server, browser, and workstation-agent version surface to 0.6.3 and incremented the workstation renderer revision to 18 so existing managed installations receive corrected filler-free Cura labels.

### Fixed

- Fixed the notification panel remaining open after the user clicked elsewhere on the page while preserving interactions inside the panel.
- Fixed Print History disappearing after 0.6.2 because the paginated API rejected browser query-string page sizes such as `per_page=10`.
- Fixed current-print status and progress collapsing into the reserved thumbnail column when no Dashboard thumbnail is available.
- Fixed managed prints stopping after the purge line with Fluidd showing paused at 0% by retaining the app-owned virtual-SD resume latch until a loaded paused file is safely released with `M24`.
- Fixed Filament Manager cancellation failing to recognize an `M25`-held file, and completed the deferred printer `START_PRINT` path after selecting a required build plate.

## 0.6.2 - 08.28.2026

### Added

- Added server-side Print History pagination with 10, 25, 50, and 100 record page sizes, a 10-record default, exact filtered totals, and First, Previous, Next, and Last controls.
- Added recurring Cura heartbeat evidence for the exact linked position-zero extruder nozzle diameter, with coalesced closed-Cura correction work whenever it drifts from the installed physical nozzle.

### Changed

- Changed Print History outcomes to preserve and display Moonraker's bounded terminal reason, including `klippy_shutdown`, `klippy_disconnect`, and `interrupted`, while retaining the canonical completed, cancelled, or failed status.
- Changed the managed Cura start boundary to embed separate resolved initial-layer and regular build-plate temperatures.
- Changed every server, browser, and workstation-agent version surface to 0.6.2 and incremented the workstation renderer revision to 17 so existing managed installations receive the corrected Cura start boundary.

### Fixed

- Fixed blocked or interrupted history records remaining displayed as in progress or legacy unknown after Moonraker reported their terminal outcome.
- Fixed Cura's saved quality-layer `material_bed_temperature` value being mistaken for the resolved managed regular bed temperature, which could falsely compare G-code 60 against profile 55.
- Fixed Cura nozzle alignment being checked only after a physical nozzle change; every heartbeat now detects and repairs a stale linked extruder setting.

## 0.6.1 - 08.28.2026

### Added

- Added regression coverage proving first-layer-only G-code evidence cannot create a regular build-plate-temperature mismatch while genuine initial-layer mismatches remain enforceable.

### Changed

- Changed managed Cura product labels to append each non-empty filament filler once, clearly distinguishing products that otherwise share a brand, material type, and color.
- Changed every server, browser, and workstation-agent version surface to 0.6.1 and incremented the workstation renderer revision to 16 so existing managed installations receive filler-qualified product labels.
- Changed the roadmap to contain only unfinished work, removing completed and duplicated historical planning entries.

### Fixed

- Fixed G-code inspection treating an initial-layer build-plate temperature as the regular build-plate temperature when Cura did not embed the regular value, which could falsely block profiles with intentionally different temperatures.
- Fixed managed Cura products with the same brand, material type, and color appearing to have duplicate names when one product has a filament filler.

## 0.6.0 - 08.27.2026

### Added

- Added transactional workstation-agent ownership of the matched Cura machine's saved print start and end G-code, including backup, rollback, manifest drift detection, and automatic reapplication.
- Added dashboard polling coverage that verifies printer, active-spool, active-plate, and inventory changes replace the displayed snapshot together.
- Added configurable automatic snapshots of the canonical Filament Manager PostgreSQL database, defaulting to every 24 hours with the newest ten automatic ZIP archives retained.
- Added validated backup download/import, exact-confirmation restore preparation, pre-restore safety snapshots, and a dedicated stopped-service database restore command that revokes restored browser sessions.

### Changed

- Changed the Dashboard and the server-side Moonraker active-spool/build-plate reconciliation default from 15 seconds to 5 seconds, with immediate refresh after reconnecting or returning to the page.
- Changed Cura synchronization to save the exact `FILAMENT_MANAGER_START_PRINT` and `END_PRINT` boundaries in the matched machine configuration instead of supplying them only through the runtime material overlay.
- Changed nozzle synchronization to reassert the managed saved start/end scripts in the same atomic machine-setting update.
- Changed every server, browser, and workstation-agent version surface to 0.6.0 and incremented the workstation renderer revision to 15 so existing managed installations receive the saved machine scripts.
- Changed Diagnostics to show database backup scheduling and recovery archives at the bottom while removing the Projection operations / Recent jobs table completely.

### Fixed

- Fixed Dashboard values remaining stale for up to 15 seconds after printer, physical spool, or build-plate changes.
- Fixed managed Cura start/end integration depending on runtime plugin interception instead of being visibly and persistently configured on the matched Cura printer.
- Fixed the v0.5.8 Cura plugin entering an infinite `getProperty`/`extruderList` recursion that could generate hundreds of megabytes of errors, repeatedly crash Cura, and destabilize the workstation.

## 0.5.8 - 08.26.2026

### Added

- Added regression coverage for the Klipper public load/unload ownership contract and reserved physical-routine calls.
- Added desktop and mobile rendered-layout coverage for the compact top-aligned login content.

### Changed

- Changed Klipper integration setup to keep the printer's physical load and unload movement under exact reserved internal macro names while Filament Manager directly owns the public commands.
- Changed the login's left column to begin at the top of the artwork and removed the oversized gap between the brand and `PRINT OPERATIONS`.
- Changed customized filament settings to use a prominent warning treatment and an explicit **Revert to Template** action.
- Clarified blocked-inspection guidance that Cura's sliced start sequence calls the Filament Manager gate before the unchanged Klipper `START_PRINT` macro; the gate does not belong inside `START_PRINT`.
- Incremented the workstation renderer revision to 14 so existing installations replace the corrected Cura runtime plugin while Cura is closed.

### Fixed

- Fixed Klipper startup failing because the app macros attempted to rename nonexistent public `UNLOAD_FILAMENT` and `LOAD_FILAMENT` commands.
- Fixed the Cura runtime plugin checking the material-less global printer stack directly, which prevented managed slices from receiving the Filament Manager start/end boundary; its generated start call now uses Cura's explicit position-zero extruder tokens.
- Fixed direct template saves leaving linked filament profile and catalog views cached with old inherited values; every affected view now refreshes immediately while preserving explicit filament overrides.

## 0.5.7 - 08.26.2026

### Added

- Added separately managed Initial Layer Build Plate Temperature across templates, filament profiles, Cura import/export, G-code inspection, and the workstation material catalog.
- Added bounded Moonraker G-code thumbnail capture, metadata-free WebP storage, authenticated thumbnail delivery, and current/history thumbnail presentation.
- Added current and historical estimated/actual print statistics plus immutable segment-derived filament cost, including explicit partial and mixed-currency handling.
- Added schema migration `a9b0c1d2e345` to backfill initial-layer bed temperature and add stored print-thumbnail fields.

### Changed

- Changed Cura material enforcement to resolve managed values through a post-initialization runtime overlay while keeping Cura's user and quality layers reserved for Cura-only quality settings.
- Changed managed Cura slicing to supply the exact `FILAMENT_MANAGER_START_PRINT` and `END_PRINT` boundaries at runtime without rewriting stored machine scripts.
- Changed Cura recovery rotation to retain the newest 15 automatic points per installation/version without counting or pruning named Administrator points.
- Changed template rows and cards to open editing directly, with JSON export and confirmed deletion moved into the template editor.
- Changed live material-segment capture to refresh actual use during printing so Dashboard filament use and cost-so-far remain current.
- Changed the complete Cura catalog to 56 entries and the required non-metadata Material Settings subset to 54.
- Changed every server, browser, and workstation-agent version surface to 0.5.7 and incremented the workstation renderer revision to 13 to force safe plugin replacement.

### Fixed

- Fixed managed material settings being copied into Cura's top user-change layer and then included when saving a custom quality profile.
- Fixed the reference Klipper configuration failing startup when no pre-existing `M600` command was available to rename.
- Fixed managed Cura prints bypassing `FILAMENT_MANAGER_START_PRINT`, which left inspection outside the pause gate and prevented exact managed-profile resolution.
- Fixed first-layer bed temperature being forced to the regular bed temperature by an incomplete material-setting contract.
- Fixed Print History omitting available Moonraker thumbnails, captured filament costs, and useful predicted-versus-actual results.

## 0.5.6 - 08.26.2026

### Added

- Added the running version to the login page.
- Added exact-name confirmed material-template deletion that removes a template from active use and Cura while retaining immutable profile and audit history.
- Added editable printer/nozzle scope controls to existing templates; linked current filament profiles move atomically when the target scope has no conflict.
- Added workstation migration coverage for repairing legacy Cura extruder-stack material references before stale managed material files are removed.

### Changed

- Changed managed Cura product and template identities from revision-specific IDs to stable semantic scope IDs so ordinary settings edits no longer invalidate Cura container stacks or previously sliced managed GUIDs.
- Changed new-template defaults to prefer the printer's currently installed physical nozzle.
- Changed blocked Print History results to distinguish a detected block condition from an actual printer pause and to explain when the required printer-side start gate was not active.
- Changed every server, browser, and workstation-agent version surface to 0.5.6.

### Fixed

- Fixed Cura reporting a managed material and its extruder stack as corrupt after a filament/template settings revision removed the revision-specific material container referenced by Cura.
- Fixed newly sliced G-code becoming unable to resolve an exact managed material profile after an otherwise valid profile edit.
- Fixed template editing omitting the associated printer and physical nozzle.

## 0.5.5 - 08.26.2026

### Added

- Added field-specific filament product validation that highlights, explains, centers, and focuses every rejected control while retaining a safe request reference in the complete error summary.
- Added regression coverage for clearing a Rainbow filament display name, conditional material modifiers, useful filament-card facts, detailed template wrapping, and recovery-request health isolation.

### Changed

- Changed detailed material-template cards to use their full width and wrap titles, printer names, nozzle facts, and values instead of truncating available text.
- Replaced identical material-setting counts on template records with the template's material Flow value.
- Changed filament cards to show diameter tolerance and current printing-temperature scope/range instead of filament diameter and nominal mass.
- Changed filament and spool identities to omit implied `None` filler and `Standard` finish values while retaining every meaningful modifier.
- Changed every server, browser, and workstation-agent version surface to 0.5.5.

### Fixed

- Fixed a valid Rainbow filament edit resubmitting the server-owned six-sample palette through the one-to-three user multicolor request contract, which could make clearing an optional display name appear to fail.
- Fixed failed named Cura backup requests temporarily marking the connected Cura agent unhealthy; those failures remain clearly retained under Recovery points and Diagnostics history.

## 0.5.4 - 08.25.2026

### Added

- Added List, Cards, and Detailed presentations for material templates with an independently remembered view preference.
- Added versioned per-template JSON downloads and an Administrator workflow to import those files into a newly scoped material type or explicitly confirmed existing-template overwrite.
- Added PEBA, ABS, and PP to the suggested material types while retaining free-form material names.
- Added regression coverage for the exact Rainbow edit/catalog failure, portable template create/overwrite operations, template catalog views, and number-input wheel safety.

### Changed

- Changed mouse-wheel gestures over focused numeric controls to scroll normally without changing the stored control value.
- Removed the Templates-page Cura-import shortcut; existing Cura materials remain available through the reviewed workstation-takeover workflow.
- Changed filament create and update transactions to validate their exact response representation before committing canonical changes.
- Changed every server, browser, and workstation-agent version surface to 0.5.4.

### Fixed

- Fixed Rainbow's valid six-color palette violating the three-color multicolor response limit, which made the entire filament catalog unreadable and caused Print settings to display `Unknown filament` even though canonical products and settings were not deleted.
- Fixed a successful filament edit being committed before a later response-serialization failure could be detected.

## 0.5.3 - 08.25.2026

### Added

- Added shared Type, Color, Filler, and Finish identity summaries across filament and spool lists, cards, selectors, measurement context, and details.
- Added regression coverage for profile-level cooling overrides and Cura fan boundary validation.

### Changed

- Changed every tracked cooling control from template-only ownership to editable filament-profile settings while retaining template inheritance for unchanged values.
- Changed Regular and Maximum Fan Speed to accept 0 through 100 percent and Regular Fan Speed at Layer to require 1 or greater.
- Changed every server, browser, and workstation-agent version surface to 0.5.3.

### Fixed

- Fixed filament profiles hiding most cooling controls even though those values can be material-specific.
- Fixed filament and spool titles/subtitles omitting important filler and finish identity.
- Fixed an isolated automatic Cura settings capture failure incorrectly marking the entire connected workstation agent as errored; capture failures now remain recovery-specific and expose bounded actionable guidance.

## 0.5.2 - 08.25.2026

### Added

- Added regression coverage for saving a completely populated template through a paired Cura workstation, including all three ironing values and every tracked settings group.
- Added reusable sanitized form-error summaries that list each rejected field and include a diagnostic correlation reference for unexpected server failures.

### Changed

- Changed template, filament print-settings, and build-plate form failures to retain actionable server error codes, HTTP status, and safe diagnostic references instead of collapsing failures into a generic rejection.
- Changed template-card grid tracks and metadata cells to enforce bounded widths for long printer, nozzle, and setting text.
- Changed every blank template value to show an explicit **Copy from another template** selector; populated active templates are selectable, while the empty-source state explains why copying is unavailable.
- Changed every server, browser, and workstation-agent version surface to 0.5.2.

### Fixed

- Fixed populated template ironing values failing during the paired-workstation Cura library build because immutable template numeric strings were formatted as database Decimal objects.
- Fixed template card content overflowing past the right edge of its card.
- Fixed validation summaries omitting the names and reasons for rejected settings even when the exact control was highlighted.
- Fixed blank template values hiding the copy feature entirely when the page found no eligible source, which made the requested workflow appear missing.

## 0.5.1 - 08.25.2026

### Added

- Added interactive Windows workstation pairing during installation, current-user PATH registration, immediate startup after successful pairing, and persistent limited logon-task startup.
- Added explicitly confirmed initialization of a fresh Cura installation from any retained recovery point captured on another paired workstation with the exact same Cura version, followed by canonical nozzle alignment and full managed-library synchronization.
- Added a per-field **Copy from** selector for blank template values, populated from every active template containing that setting.
- Added permanent printer ownership for every physical nozzle and exact physical-nozzle references for material templates.

### Changed

- Changed ironing management to track only flow, speed, and line spacing per material; Cura quality profiles now exclusively control whether ironing is enabled.
- Changed the managed Cura Material Settings contract from 54 to 53 non-metadata keys and advanced the workstation renderer revision so existing agents replace the prior managed plugin manifest.
- Added schema migration `e7f8a9b0c123` to remove the retired material-profile ironing-enable column; its historical values are intentionally not reconstructed on downgrade.
- Changed template numeric controls to expose their supported browser constraints before submission while retaining sanitized server-side field validation.
- Changed template cards to show the printer directly below the title and the exact nozzle code, diameter, and material in the details without rendering stored description text.
- Changed Spools, Filaments, Build Plates, and Nozzles catalog grids to equal-height cards with bounded, truncated text; Filament and Nozzle list rows now open directly without redundant action buttons.
- Added schema migration `f8a9b0c1d234` to backfill printer-owned nozzles and exact template/nozzle scope, rejecting genuinely ambiguous legacy ownership instead of guessing.

### Fixed

- Fixed fresh Windows installations leaving `filament-manager-agent` unavailable from normal prompts and leaving the registered startup task stopped.
- Fixed fresh Cura workstations being unable to reuse a compatible backup captured by an existing workstation.
- Fixed invalid ironing values producing poor save guidance by preserving exact field-level validation, native invalid highlighting, centered scrolling, and keyboard focus.
- Fixed diameter-only template scope allowing two physical nozzles on one printer to share an indistinguishable template identity.

## 0.5.0 - 08.25.2026

### Added

- Added a Filaments sub-navigation with separate **Catalog** and **Print settings** views, plus a current exact-scope matrix for every filament, printer, and nozzle combination.
- Added creation of an additional filament print-settings scope from any compatible active material template.
- Added PostgreSQL, frontend, and rendered workflow regression coverage for multiple current print-settings scopes, exact-scope editing, creation, duplication, inheritance, density changes, navigation, and responsive actions.

### Changed

- Changed filament details to separate physical product editing from printer/nozzle-specific print settings and to expose exact Edit, Compare, and Cura JSON export actions on every current scope.
- Changed the former top-level **Profiles** page to **Filaments → Print settings**; the legacy `/profiles` browser path now redirects to `/filaments/settings` without changing backend API paths.
- Enlarged the live printer status pill substantially inside the existing Dashboard printer card while preserving the card's dimensions and responsive layout.
- Updated every server, browser, workstation-agent, documentation, and test version surface to 0.5.0.

### Fixed

- Fixed template saves updating profiles from a product-level template pointer instead of each current exact profile's inherited template revision.
- Fixed template propagation reviving a historical profile after its printer/nozzle scope had been rebased, density changes updating only one scope, and duplication copying the globally newest profile instead of the selected exact scope.
- Fixed template activation changes trying to serialize an expired asynchronous database record after commit.

## 0.4.3 - 08.25.2026

### Added

- Added regression coverage for recovery-point ordering, complete stored-validation visibility, historical diagnostic labelling, and operation-scoped Cura failure notifications.

### Changed

- Changed Recovery points to show saved Cura configurations before recent backup-request history.
- Changed Diagnostics to display every immutable check included in a stored validation summary and to distinguish the recorded validation time from current live checks.
- Changed retained Cura deployment and recovery failures to appear as bounded history when they no longer represent a current condition.

### Fixed

- Fixed Diagnostics showing error and warning totals while hiding the non-recovery validation cards responsible for those counts.
- Fixed failed named Cura backup requests creating duplicate, permanently active material-synchronization notifications; genuine synchronization alerts now converge by workstation and newest operation state.
- Fixed generic Cura notification rows duplicating the more useful sanitized deployment cause in Recent errors.

## 0.4.2 - 08.24.2026

### Added

- Added a formal responsive login experience with purpose-built Workshop Navy artwork showing a delta 3D printer and colored filament spools.
- Added bounded in-Cura saving for tracked values on known managed templates and filament profiles. The managed plugin retains an operator's pending value, the agent reports the complete material state, and the server saves and resynchronizes it through the existing validated direct-save path.

### Changed

- Changed the managed Cura plugin to add its 54 required Material Settings keys without replacing unrelated operator selections, and to remove only cleanup-only retired selections.
- Changed all server, frontend, and workstation-agent version surfaces to 0.4.2 and advanced the managed Cura renderer revision so existing installations receive the corrected plugin automatically.

### Fixed

- Fixed Cura 5.13 ironing verification using the nonexistent `ironing_speed` key instead of Cura's current `speed_ironing` definition.
- Fixed `limit_support_retractions` remaining in an installed 55-key manifest when a rejected automatic Cura backup upload prevented the workstation agent from reaching its pending library deployment.
- Fixed valid Cura setting-visibility backups being rejected by the server even after the workstation agent captured them safely, and isolated future backup upload failures so material, nozzle, and restore claims continue.
- Fixed managed values changed in Cura being immediately restored from the old material file before the change could be saved to Filament Manager.

## 0.4.1 - 08.24.2026

### Added

- Added regression coverage proving retired Cura material controls are excluded from the managed catalog, import, editor, and emitted profile while remaining available only for one-way workstation cleanup.
- Added a large live printer-status card to Dashboard with Moonraker/Klipper availability, idle/printing/paused/finished/fault state, bounded print progress, current G-code filename, and available nozzle, bed, and chamber temperatures. The card refreshes every 15 seconds without making inventory data depend on printer availability.

### Changed

- Removed **Limit Support Retractions** from templates, filament profiles, managed Cura material output, takeover discovery, the required Material Settings plugin selection, and the operator checklist. Existing managed values are cleanup-only retired data and are removed from Cura during the next library synchronization.
- Updated the compatible frontend build dependency from Vite 7.3.6 to 8.2.2 after full CI and isolated local validation.
- Changed all server, frontend, and workstation-agent version surfaces to 0.4.1.

### Fixed

- Fixed the List/Cards/Detailed selector and its native option list rendering with white-on-white colors under dark GUI profiles; select controls now use the active theme's semantic text and surfaces.
- Fixed automatic and named Cura recovery capture rejecting Cura's valid setting-visibility presets because their setting names intentionally use key-only lines rather than `key = value` pairs, and replaced the generic capture failure for malformed or unsafe files with a bounded actionable reason.

## 0.4.0 - 08.24.2026

### Added

- Added automatic centered scrolling and keyboard focus for the first template setting rejected by browser or server validation.
- Added independently remembered **List**, **Cards**, and **Detailed** catalog presentations to Spools, Filaments, Build Plates, and Nozzles.

### Changed

- Changed Build Plates to use compact responsive plate cards, smaller imagery and fact blocks, readable side grouping, and intrinsic-width desktop action rows instead of page-wide buttons.
- Changed Spools to use the full available catalog width without a permanent selection card; selecting a spool from any presentation now opens its complete details and actions in an accessible modal.
- Changed compact and detailed inventory cards to retain the same complete actions through a selected-item detail modal, while list presentations keep information-dense horizontal rows.
- Tightened shared page headers, cards, toolbars, tables, status grids, empty states, and section spacing, and allowed catalog, integration, workstation, printer, and build-plate records to use available desktop width more efficiently without removing information.
- Changed shared action groups to wrap compactly on desktop while retaining full-width 44-pixel touch actions on narrow mobile layouts.
- Changed build-plate editing to offer only rectangular or round geometry. Rectangular plates show width and depth, round plates show diameter, and hidden shape-specific dimensions are cleared when saved.
- Changed template editing to refresh the selected template immediately before opening so routine Cura-originated updates do not leave the editor on an already-stale version.
- Changed all server, frontend, and workstation-agent version surfaces to 0.4.0.

### Fixed

- Fixed action buttons on Build Plates, Nozzles, Diagnostics, and spool details stretching across their entire containers because the shared action group used a one-column grid.
- Fixed invalid template settings appearing only as a generic save failure at the bottom of a long modal; the exact control now has a prominent danger treatment, an inline sanitized reason, `aria-invalid` metadata, and centered focus.
- Fixed the terse **Template changed; reload and retry** response obscuring a genuine concurrent update; a remaining conflict now explains that the editor must be reopened to review current values.

## 0.3.3 - 08.22.2026

### Added

- Added per-Cura-installation material-setting verification receipts with exact expected/exposed counts, bounded missing/extra keys, required Material Settings/Klipper Settings package versions and readiness, catalog checksums, and verification times on Cura Workstations and Diagnostics.
- Added a PostgreSQL migration and regression coverage for microsecond-sized manual system-job versions in the durable projection outbox.
- Added inheritance regression coverage for both one-sided Regular Fan Speed and Maximum Fan Speed customizations when a linked template changes.
- Added template-only Cura controls for Print, Infill, Wall, Top Surface Skin, Top/Bottom, Support, and Travel Acceleration, with silently enforced acceleration-control and travel-acceleration toggles.
- Added recovery coverage proving complete bounded non-sensitive machine/extruder options, including start/end G-code, survive Cura backup and restore.
- Added ironing controls to both templates and filament profiles and to the complete tracked Cura settings checklist.
- Added live named-backup request status and sanitized workstation-agent failure details to Cura Workstations.

### Changed

- Changed the managed Cura extension to reapply the authoritative 55-key Material Settings plugin selection after manual drift and verify every key against the active machine definitions before reporting healthy.
- Changed all print-speed controls and cooling controls other than Initial Fan Speed to template-only ownership; existing current profiles receive new immutable inherited snapshots instead of rewritten history.
- Changed pressure advance back to template-and-filament ownership while keeping Klipper smooth time and acceleration template-only.
- Changed Cura flow tracking to one primary Flow value and retired feature-specific flow controls.
- Changed temperature tracking to exactly Printing Temperature, Build Volume Temperature, and Build Plate Temperature; default, standby, initial/final print, and initial-bed controls are retired and no longer emitted.
- Changed Initial Fan Speed from a hidden forced zero to an editable template/profile setting.
- Changed the outbox aggregate-version column from 32-bit integer to `BIGINT` and advanced the expected database schema to `d6e7f8a9b012`.
- Changed all server, frontend, and workstation-agent version surfaces to 0.3.3.

### Fixed

- Fixed Material Settings or Klipper Settings plugin absence, disabled packages, unsupported keys, and an unopened post-upgrade Cura installation being indistinguishable from a healthy material synchronization.
- Fixed managed Cura template edits failing workstation heartbeats with a Pydantic validation error when the new template fan range conflicted with a linked filament's explicit fan customization.
- Fixed manual Spoolman reconciliation and other system projection actions failing at commit with `NumericValueOutOfRange` because their microsecond timestamp identities exceeded PostgreSQL's 32-bit integer range.
- Fixed Cura nozzle synchronization changing only the global machine stack instead of the exact linked position-zero extruder's `machine_nozzle_size`; recovery now requeues canonical nozzle alignment before material synchronization.
- Fixed canonical net spool-weight corrections repeatedly failing through Spoolman's gross-scale measurement endpoint; corrections now use the supported `remaining_weight` update and the upgrade coalesces/retries existing rows immediately.
- Fixed recovered manual recurring jobs remaining as permanent dead Projection Queue debt even after later periodic synchronization succeeded.
- Fixed explicit named Cura backups after a reset being silently rejected by automatic reset protection and exposing only a generic diagnostics error.
- Fixed pending Projection Queue retries appearing healthy without explaining how many had failed before or when they would retry.
- Fixed retired flow/temperature keys lingering in old Cura custom profiles, unsafe workstation paths being able to reach the UI, and obsolete failed library deployments remaining actionable after a newer full-library synchronization succeeded.

## 0.3.2 - 08.21.2026

### Added

- Added filament duplication through the normal Add Filament workflow, copying product fields, the current linked template, and sparse explicit Cura customizations without copying spools, print history, calibrations, or NFC bindings.
- Added named full Cura backup requests, editable backup names/descriptions, durable confirmed deletion of individual backups, and intentional same-content named recovery points alongside content-deduplicated automatic snapshots.
- Added safe Cura2Moonraker behavior-preference backup/restore while preserving current local Moonraker URLs and API keys, plus closed-Cura exact existing-variant nozzle updates with local machine backups.
- Added physical nozzle details, bounded job/file metadata, timing and material-use details, and authenticated range-capable moonraker-timelapse video links to Print History.
- Added derived per-gram purchase cost to every priced physical spool and a currency-safe weighted product cost basis for Cura print-cost estimates.
- Added an actionable Diagnostics failure summary that always retains the newest sanitized cause for every failing projection type, even when another repeating error fills the recent log.

### Changed

- Changed filament customization fields to use a stronger border, inset accent, background, and ownership badge so template differences are immediately visible.
- Changed Cura Workstations to distinguish synchronized managed materials, unmanaged pre-takeover sources, and user-saved custom print profiles instead of describing all counts as existing profiles.
- Changed physical nozzle installation to queue safe Cura machine-variant alignment and a subsequent current material-library synchronization on managed workstations.
- Changed all server, frontend, and workstation-agent version surfaces to 0.3.2 and advanced the expected database schema to `b4c5d6e7f890`.
- Changed recurring projection scheduling to supersede the prior terminal attempt before queuing its replacement. The v0.3.2 migration retires obsolete recurring and reconstructable Spoolman metadata failures while requeuing non-reconstructable Spoolman work such as weight adjustments.

### Fixed

- Fixed optional Moonraker spool-preflight catalog failures failing the entire physical-state reconciliation, repeatedly accumulating dead projection jobs, and logging the same warning on every poll. The catalog now has an actionable per-printer Diagnostics status, transition-based warnings, and successful recurring reconciliation that supersedes the older dead rows.
- Fixed Print History omitting the exact captured physical nozzle and other useful Moonraker/Cura job details, and removed the internal G-code SHA-256 value from the browser details.
- Fixed linked and synchronized Cura workstations appearing to have zero material profiles because the displayed count excluded the managed Filament Manager library.
- Fixed full Cura recovery excluding all Cura2Moonraker plugin settings when only its credentials and endpoints required exclusion.
- Fixed old successful projection recovery leaving hundreds of dead rows actionable and fixed older Spoolman causes being hidden when repeated Moonraker errors consumed the bounded recent-error list.

## 0.3.1 - 08.20.2026

### Added

- Added optional Bugsnag reporting for React failures, browser performance, sanitized FastAPI request failures, and terminal worker/job failures.
- Added an application-level React error boundary, a safe reload screen, runtime browser monitoring configuration, and release-aware source-map upload support for authorized CI builds.
- Added privacy and failure-isolation tests covering disabled monitoring, configuration validation, event sanitization, polling suppression, exact Content Security Policy destinations, duplicate throttling, and source-map removal from the runtime image.

### Changed

- Changed all server, frontend, and workstation-agent version surfaces to 0.3.1.
- Changed browser monitoring to load only when explicitly enabled, normalize application routes, omit page attributes and user identifiers, disable error-session reporting, replace the private origin, suppress high-frequency polling spans, and prevent distributed tracing.
- Changed server monitoring to report generic exception classes plus a small allowlist of operational context without raw messages, request data, credentials, URLs, hostnames, or external response bodies. Repeating worker reports are throttled, and only terminal outbox failures are reported.
- Changed production frontend builds to create hidden source maps, upload them only on an authorized direct push with the separate `BUGSNAG_UPLOAD_API_KEY` repository secret, and remove them before the runtime image is assembled.

### Fixed

- Fixed browser render failures presenting a blank application with no recovery action.
- Fixed production browser, API, and worker failures depending solely on local logs for actionable error visibility.
- Fixed optional external monitoring being able to expand the default network policy when it is disabled; Bugsnag destinations are added to the Content Security Policy only while their matching feature is enabled.

## 0.3.0 - 08.20.2026

### Added

- Added separate Retraction Retract Speed and Retraction Prime Speed tracking plus Cooling controls for Regular Fan Speed, Maximum Fan Speed, Regular Fan Speed at Layer, Minimum Layer Time, and Minimum Speed across templates, profiles, imports, exports, comparison, G-code inspection, migrations, and Cura synchronization.
- Added a completed-calibration recommendation review with direct filament-profile application, exact-name-confirmed linked-template application/cascade, and confirmed deletion for unapplied calibrations.
- Added bounded build-plate picture upload, secure metadata-stripped WebP normalization in PostgreSQL, plate-card imagery, editable unique nozzle codes, and an installed-nozzle card highlight.
- Added eight distinct GUI color profiles—three light and five dark—under Settings, plus semantic Activity card colors and quick actions for selecting and adding filament.
- Added single-account username, display-name, and password editing with other-session revocation.

### Changed

- Changed the application to exactly one Administrator account. An empty database creates `admin` / `admin` and forces a first-login password change; existing single-account credentials remain unchanged, and Docker username/password variables plus the bootstrap service were removed.
- Changed Rainbow from a display type to a fixed color and changed Multicolor to one, two, or three product-specific samples so unrelated multicolor filaments no longer share one palette.
- Changed profile Cura exports to download JSON attachments, enlarged the independently decodable centered spool icon in QR labels, and advanced the workstation renderer revision to 5.
- Changed Dashboard Quick Actions to a full-width horizontal card and removed the Workshop Operations diagnostics card. Simplified Integrations by removing duplicated operational status and the top Diagnostics action.
- Changed Initial Fan Speed to a silent deterministic zero, hid the legacy Retraction Speed alias, and kept the requested canonical retract and prime speeds independent during Cura edits.
- Changed all server, frontend, and workstation-agent version surfaces to 0.3.0.

### Fixed

- Fixed 1,125 recovered recurring projection failures remaining reported as actionable dead queue debt; successful recurring work now supersedes older dead rows and the migration converts accumulated periodic failures.
- Fixed Moonraker state failures lacking enough sanitized context by identifying the failing active-spool, drift-repair, catalog, or build-plate sub-operation.
- Fixed completed-print G-code inspection warning that no exact managed profile could be resolved even when the file contained a known deterministic managed material GUID.
- Fixed the filament color dropdown not reopening the known-color list while retaining support for a newly typed color.
- Fixed a prime-speed-only Cura change clearing the independent retraction retract speed during settings merge.

## 0.2.6 - 08.19.2026

### Added

- Added an easy-to-find, full-color 128 x 128 app icon for Pushover and other notification services.

### Changed

- Documented the reusable notification icon in the main README.
- Changed spool-label QR codes to use high error correction and embed each filament's solid, multicolor, or rainbow spool icon directly in the center while retaining only the stable spool URL as QR data.
- Changed all server, frontend, and workstation-agent version surfaces to 0.2.6.

### Fixed

- Fixed the repository lacking an exact-size, opaque app icon suitable for notification-service uploads.
- Fixed label previews showing the color indicator separately from the downloaded and printed QR image.

## 0.2.5 - 08.18.2026

### Added

- Added automatic sanitized Cura configuration recovery points for printers, extruders, custom profiles, visibility, safe preferences, and semantic plugin inventory, retaining the ten newest distinct points per workstation installation and Cura version.
- Added an Administrator review-and-confirm recovery workflow on Cura Workstations with exact-version enforcement, local pre-restore backup, atomic replacement, rollback, and Diagnostics readiness/error reporting.

### Changed

- Changed the managed Cura plugin to keep the Material Settings plugin's enabled-setting list aligned with the complete central catalog after Cura initialization and after a recovery restore.
- Changed Cura product materials without a manufacturer to appear under the `Unknown` brand instead of a Filament Manager brand.
- Changed active-spool reconciliation retries to remain within the configured real-time polling interval, keeping physical state recognition within one minute while Moonraker is reachable.
- Changed filament cards to show vendor, material/color/display name, and filler/finish as three clear identity lines, and changed filament editing to select the current or another compatible current template.
- Changed synchronized Cura material descriptions to show `Filament Filler` and `Filament Finish` on separate lines, using `None` for empty values.
- Changed Cura workstation protection to preserve the last known-good recovery point when a reset, missing printer, or large configuration deletion is detected; managed materials remain canonical and synchronize separately after recovery.
- Changed the workstation service sandbox to permit both discovered Cura data and configuration roots required for safe preference capture and restoration.
- Changed the workstation deployment renderer revision to 4 so upgraded agents replace earlier generated material files.
- Changed all server, frontend, and workstation-agent version surfaces to 0.2.5.

### Fixed

- Fixed a malformed historical Moonraker record preventing otherwise successful print-history scans from recording their synchronization checkpoint.
- Fixed structured display palettes being rejected by Spoolman text custom fields, which left canonical filament projections newer than their acknowledgements.
- Fixed manual material-type and color-name inputs losing focus to the modal close button after every keystroke.
- Fixed filament editing referring to a superseded template revision and therefore omitting the current linked template and compatible alternatives.
- Fixed the managed Cura plugin constructing Cura's machine manager during plugin registration, which could restore the active machine before Cura initialized its translation catalog and crash Cura 5.13 at startup; upgraded agents now also invalidate and replace the earlier plugin even when material settings are unchanged.
- Fixed a reset Cura installation having no application-guided way to restore its printer, extruder, custom profile, visibility, and safe preference configuration after Cura account plugins are reinstalled.

## 0.2.4 - 08.18.2026

### Added

- Added sanitized structured API validation details and accessible red per-field messages in template and filament material-setting editors.
- Added automatic Cura favorites for every synchronized `Template <material type>` entry.
- Added bounded workstation cleanup for user-created Cura quality-change profiles, including pre-change backup, recoverable-format repair, corrupt-profile quarantine, drift detection, and rollback coverage.
- Added a maintained plain-text checklist of all 54 Cura Material Settings plugin selections tracked by Filament Manager, with automated central-catalog parity coverage.

### Changed

- Changed the server-supplied approved Cura material-setting catalog to be the authoritative list used by the workstation deployment and Cura enforcement plugin.
- Changed the managed Cura plugin to mirror each selected managed material's explicit values into Cura's top supported user layer, ensuring built-in and custom quality profiles cannot supersede filament-specific settings.
- Changed user-created Cura main/custom profiles to remain workstation-owned and unsynchronized while removing only centrally managed material keys; all unrelated quality, purpose, and model settings remain intact.
- Changed the Cura deployment contract to schema 3; upgrade every paired workstation to the 0.2.4 agent before expecting profile cleanup or the updated enforcement plugin.
- Changed all server, frontend, and workstation-agent version surfaces to 0.2.4.
- Changed solid, multicolor, and rainbow inventory swatches to share the same physical spool silhouette; multicolor uses its selected hard color segments while rainbow uses a distinct continuous spectrum.

### Fixed

- Fixed template saves reporting only `Request validation failed` without identifying the invalid control, constraint, or reason.
- Fixed synchronized templates not being automatically favorited in Cura.
- Fixed Cura quality and sidebar layers taking precedence over managed material values exposed by the Material Settings plugin.
- Fixed recoverable duplicate-section user profiles continuing to trigger Cura corruption warnings, and isolated malformed profiles so Cura no longer attempts to load them.
- Fixed multicolor and rainbow fills replacing the spool illustration instead of coloring its filament regions.

## 0.2.3 - 08.18.2026

### Added

- Added an idempotent `Template ASA` starting profile for each configured printer/nozzle scope so an existing Cura ASA profile has a canonical takeover target.
- Added an explicit two-stage Cura takeover dialog where Administrators map each reported material or saved print profile to an existing template, then review the complete batch before confirmation.
- Added clear visual highlighting for every filament setting that is explicitly customized instead of inherited from its linked template.
- Added custom named filament colors, two- or three-color palettes, and rainbow spool swatches across inventory, dashboard, and labels.
- Added complete filament and spool correction editors plus safe delete-or-archive actions.
- Added automatic empty-spool tare calculation from the entered filament amount and optional full-spool scale weight.

### Changed

- Changed the filament settings editor to render the complete effective template-linked values while continuing to persist only semantic differences as sparse filament overrides.
- Changed filament settings into Cura-like temperature, flow, speed, retraction, cooling, support, dimensional, filament, Klipper, and build-plate groups with no catch-all advanced section.
- Changed customized-setting highlighting to update immediately while editing and remain visible after saving.
- Changed user-facing numeric values to compact field-specific precision with no displays beyond two decimal places.
- Changed completed, failed, and cancelled jobs to deduct only actual Moonraker-reported segment use from each exact spool, without a predicted fallback or duplicate deductions.
- Changed filament colors to remain editable until the filament has retained spool-use or print history, after which identity is locked for historical consistency.
- Changed overlapping Cura retract-speed and maximum-fan aliases to use one canonical application control while still writing the required deterministic alias values to Cura.
- Changed workstation discovery to keep named Cura materials and saved print profiles selectable even when they contain no tracked literal overrides or only safely omitted expressions.
- Changed all server, frontend, and workstation-agent version surfaces to 0.2.3.

### Fixed

- Fixed periodic workstation heartbeats invalidating an open Cura mapping review with `Workstation changed; reload and retry`; takeover now locks against the exact reviewed Cura source catalog instead of unrelated workstation activity.
- Fixed the workstation agent using HTTPX's bundled public CA file instead of the operating-system trust store, which prevented heartbeats and Cura profile discovery on installations secured by a locally trusted private CA.
- Fixed duplicate retraction-speed and maximum-fan controls appearing under both grouped profile settings and Additional Cura Material Settings.
- Fixed Cura takeover showing zero importable profiles when discovered saved profiles contained only inherited Cura expressions or no literal settings tracked by Filament Manager.
- Fixed **Back to mappings** returning to a workstation card without an unmistakable source-to-template mapping screen.
- Fixed the Arch workstation service failing Cura deployment when its platformdirs title-case state root did not exist beneath systemd read-only home protection.
- Fixed new-spool gross weight being rejected instead of deriving empty-spool tare from gross weight minus filament amount.
- Fixed setup mistakes lacking a safe delete path and incomplete spool/filament editors preventing correction of original setup fields.
- Fixed terminal failed and cancelled jobs not reducing exact spool inventory from their reported actual filament use.

## 0.2.2 - 08.17.2026

### Added

- Added physical nozzle inventory with diameter, construction material, lifecycle status, printer installation history, completed-print count, and total filament use.
- Added completed-print counts to each spool and build-plate side. A completed print counts once for every distinct spool used, including distinct M600 material segments.
- Added manual Side B creation for an existing physical P-number plate; the new `P<number>b` side remains unavailable until Moonraker discovers its exact same-named mesh.
- Added a dedicated Diagnostics page for connection, synchronization, worker, queue, and operational status; bounded recent errors; persisted recovery-validation results; safe projection rebuilds; and job retry/reconciliation controls.
- Added the running Filament Manager version to the application shell and Diagnostics, plus a cached Diagnostics comparison with the newest non-draft GitHub release, including testing prereleases.
- Added `filament-manager-cli verify` for read-only recovery validation and `filament-manager-cli rebuild-projections --confirm` for safe full projection requeueing.
- Added an atomic one-time Cura takeover that lists every discovered source with an existing-template selector, allows any source to remain unmapped, reviews all choices together, and records source/template provenance.
- Added read-only discovery of saved Cura print profiles during one-time takeover, including merged global/first-extruder settings, machine and quality metadata, tracked literal settings, and safely omitted expression counts.
- Added Arch Linux and Windows workstation-agent uninstallers that remove the per-user service/task, executable, pairing credential, local state, and agent backups while leaving Cura's current managed library in place.
- Added an authenticated **Download log** action on Diagnostics that exports the current bounded, sanitized operational report as a plain-text file.

### Changed

- Moved live connection, synchronization, worker, queue, and error information from Dashboard, Printers, Integrations, and Cura Workstations into Diagnostics.
- Changed template, filament-profile, calibration, workbook-import, and managed Cura edits to save directly as current settings, automatically queue projections, and keep versioned snapshots only as hidden immutable history.
- Changed template saves to update every linked filament profile immediately while preserving each explicit customized setting, even when its value temporarily matches the new template.
- Changed Cura takeover to map each selected source directly to an existing template, allow each source/template once, ignore unmapped sources, and apply all template changes plus linked-profile inheritance in one confirmed transaction.
- Changed print-profile import to accept only settings tracked by Filament Manager and omit unevaluated Cura expressions.
- Changed printer nozzle editing to use installed physical nozzle records; installation and removal are recorded as append-only lifecycle events.
- Changed all server, frontend, and workstation-agent version surfaces to 0.2.2.
- Changed `LOAD_FILAMENT`, `FILAMENT_MANAGER_LOAD_TARGET`, and M600 replacement selection to use a dedicated live manual-load catalog without a hidden macro-variable prerequisite. Non-empty projected spools may use their newest exact profile or linked template temperature, while Cura print preflight still requires a current exact profile.
- Changed direct non-null Spoolman selections into guarded Fluidd target confirmations: the worker restores the last physical ID until the operator confirms an existing load or completes the unload/load routine.
- Changed the application shell to show only an icon-labelled Logout action and directional sidebar chevrons, and moved the persistent light/dark theme control to Settings.
- Changed `SELECT_BUILD_PLATE` without parameters to build its chooser live from Klipper's saved exact P-number meshes.
- Changed workstation installers to state clearly whether they are performing a fresh installation or an upgrade while retaining conditional restart and rollback behavior.
- Changed stale Cura-agent diagnostics to identify the last contact and recommend checking or upgrading the workstation service.
- Changed aggregate Moonraker reconciliation errors to retain bounded exception-class counts without exposing tracebacks, external responses, URLs, or database details.

### Fixed

- Fixed the missing workflow for adding the second printable side of an existing physical build plate.
- Fixed operational status being fragmented across unrelated pages instead of providing one reviewable diagnostics surface.
- Fixed pre-takeover Cura preservation lacking a clear per-source destination selector and one atomic completion step.
- Fixed saved Cura print settings being absent from the one-time takeover import and therefore unavailable for preservation before authoritative synchronization.
- Fixed user-facing material workflows requiring draft creation, publication, per-filament template-update confirmation, or manual Cura deployment instead of direct saves and automatic synchronization.
- Fixed manual filament loading dead-ending with “Select a Target Spool” even after `FILAMENT_MANAGER_LOAD_TARGET` was run.
- Fixed valid non-empty Spoolman spools being hidden from manual loading solely because they lacked a current exact printer/nozzle print profile.
- Fixed rerunning M600 during an unfinished selection reporting only that a workflow was active instead of reopening the exact-spool chooser.
- Fixed direct Spoolman selections disappearing without a safe way to use them as the requested physical target.
- Fixed the build-plate selector requiring static per-mesh macros whenever another valid mesh was saved.
- Fixed Klipper startup failing when a configuration transfer or editor collapsed an empty catalog-revision macro literal.
- Fixed Diagnostics comparing the canonical PostgreSQL schema with the superseded pre-0.2.2 Alembic revision.
- Fixed fractional Spoolman remaining-weight values repeatedly creating the same usage event and dead reconciliation job after PostgreSQL rounded the stored mass.
- Fixed a failed live-print capture expiring its SQLAlchemy printer object and causing `MissingGreenlet` during subsequent Moonraker history reconciliation.

## 0.2.1 - 08.13.2026

### Added

- Added canonical print history synchronized from Moonraker, including exact printer, spool, material-profile revision, build-plate side, G-code hash, slicer metadata, predicted/actual use, immutable M600 material segments, and explicitly unresolved legacy records.
- Added bounded G-code inspection of Moonraker metadata and Cura headers, with profile mismatch evidence and an Administrator setting that changes the default warn-and-continue behavior to fail-closed blocking in Fluidd.
- Added append-only print assessments with Excellent, Successful, Acceptable, and Failed ratings, optional defect tags, notes, and profile-version success statistics.
- Added full dimensional calibration for X, Y, Z, holes, shafts, and wall thickness, including Cura expansion/flow results, material shrinkage, and non-applying printer-geometry recommendations.
- Added two-to-four-column profile/template revision comparison with difference-only rows, cross-scope warnings, success rates, low-sample labels, and template N/A states.
- Added account editing, activation controls, temporary-password reset, forced password replacement, build-plate maintenance ledgers/reminders, explicit active spool/plate clearing, responsive mobile data cards, and a persistent per-user notification center.

### Changed

- Changed new local accounts to require replacement of their Administrator-supplied temporary password before any other application route is available.
- Changed Moonraker print-state polling to every five seconds by default and added complete supported-history import plus incremental reconciliation.
- Changed the supplied Klipper macro reference to gate optional blocking inspection before exact-spool selection while preserving the existing `START_PRINT`, `END_PRINT`, motion, cancellation, and purge implementations.
- Changed build plates to use configurable cleaning and mesh-calibration thresholds based on both elapsed days and completed-print counts.
- Changed all server, frontend, and workstation-agent version surfaces to 0.2.1.

### Fixed

- Fixed a preflight-paused print being able to record the previously loaded spool as its starting material before the requested spool was physically loaded.
- Fixed a completed live print being duplicated when Moonraker repeated its terminal state or the same job later appeared in history.
- Fixed M600 print-history segments lacking their own derived length and weight totals.
- Fixed a reactivated operator notification remaining read after the underlying condition recurred.

## 0.2.0 - 08.13.2026

### Added

- Added a Cura Workstations preservation workflow that imports selected reported Cura materials as source-tracked draft templates for review and publication before takeover.
- Added duplicate-safe Cura template-import provenance plus a server-side guard that blocks authoritative management until every selected import is active and published; distinct imported source variants can coexist with a base template of the same material type.
- Added repeated-install regression coverage for the Arch Linux and Windows workstation installers.
- Added a difference-only material comparator for profile-to-profile and profile-to-template-revision review, including complete canonical and additional Cura settings.
- Added Cura material-GUID print preflight with exact matching-spool choices in Fluidd, profile-specific unload/load temperatures, persistent physical-spool state, bounded printer catalog synchronization, and a complete Klipper/Moonraker macro reference.
- Added guarded manual load, unload, `M600`, active-spool, cancellation, purge-more, and resume paths that reuse the printer's existing physical routines.
- Added direct template-revision links, sparse per-filament overrides, complete resolved snapshots, inherited/customized field indicators, and per-filament template-update review.
- Added draft-only intake of setting changes made to known managed Cura templates and product materials; unchanged content is ignored, unknown or new Cura materials are rejected, and publication remains an explicit application action.

### Changed

- Changed both workstation installers to perform safe in-place upgrades when run again, preserving pairing configuration, Cura backups, and agent state while refreshing managed code and service/task definitions.
- Changed installer upgrades to restart the agent only when it was already running and to restore the previous standalone executable if replacement fails.
- Changed material comparisons to allow any printer/nozzle pairing while clearly warning when either scope dimension differs.
- Changed Inventory **Set active** to **Load spool**. The request now opens the confirmed printer workflow without changing canonical or Spoolman active state early.
- Changed 15-second Moonraker reconciliation to repair direct active-ID drift to the last completed physical Klipper state before synchronizing the application.
- Changed the server, frontend, and workstation-agent package versions to 0.2.0.
- Changed every template's application and Cura identity to `Template <material type>` under the `Template` brand, while continuing to synchronize one material entry for every published filament profile.
- Changed a published template update to require separate confirmation for each linked filament; confirmation creates a reviewable draft and preserves that filament's explicit overrides.

### Fixed

- Fixed overlong automatic Moonraker audit correlation IDs causing PostgreSQL `StringDataRightTruncation` errors in the worker.
- Fixed worker error reporting attempting to reuse an aborted database transaction, which obscured the original Moonraker synchronization failure with `PendingRollbackError`.
- Fixed repeated workstation-agent installation being unsafe while the existing agent executable or service task was running.
- Fixed aborted spool changes being able to leave a future target recorded as active: unload now clears only after motion completes, and load sets the new ID only after motion completes.
- Fixed the high-severity transitive `nanoid` development dependency advisory by updating the locked package to 3.3.18.
- Fixed profile/template ownership being implicit: profile details and history now identify the exact linked template revision and which settings are inherited or customized.

## 0.1.6 - 08.12.2026

### Added

- Added PostgreSQL-coordinated Moonraker polling for active spool and build-plate state every 15 seconds and sanitized printer information every 5 minutes.
- Added structured web, worker, scheduler, outbox, API rejection, validation, and Moonraker synchronization logs with error details and tracebacks where safe.
- Added browser-console diagnostics for every API request, including method, path, status, correlation ID, and safe rejection or network-error details.
- Added a shared accessible grouped-editor dialog and applied it to build plates, plate sides, printers, filaments, material profiles, templates, Cura imports, spools, users, and calibration setup.
- Added active-printer state to spool API responses and visible active indicators in inventory.

### Changed

- Changed the configured printer's active spool to follow Moonraker's supported Spoolman selection automatically, including selection changes and clearing.
- Changed in-app active-spool selection to update canonical state immediately in the same transaction that queues the Moonraker request.
- Changed Build Plates and Printers to display automatic synchronization freshness instead of requiring manual synchronization buttons.
- Changed Build Plates and Printers to use full-width summaries, grouped facts, side-by-side surface/status sections, and consistent edit actions instead of narrow cards and fold-down forms.
- Changed material setting editors to keep every supported Cura field visible in named groups instead of hiding additional settings in a fold-down section.
- Changed the dashboard, spool inventory, build plates, and printers to refresh operational state every 15 seconds.
- Changed the server and workstation-agent package versions to 0.1.6.

### Fixed

- Fixed printer and build-plate information remaining stale until a broken manual synchronization request was attempted.
- Fixed spool selections made through Klipper, Moonraker, or Spoolman not being reflected as active in Filament Manager.
- Fixed failed background scheduling or job claiming being able to stop ongoing synchronization without a diagnostic traceback.
- Fixed editing controls being inconsistently embedded, hidden, or expanded across different pages.

## 0.1.5 - 08.11.2026

### Added

- Added projection-aware Spoolman readiness checks, automatic managed custom-field provisioning, complete API pagination, and duplicate-safe managed UUID discovery.
- Added physical build plates with independent Side A and Side B records. `P4` represents Side A and `P4b` represents Side B of the same physical P4 plate.
- Added a plate description plus per-side surface material, smooth/textured finish, notes, mesh availability, mesh check time, and mesh calibration time.
- Added Administrator-triggered Moonraker synchronization that automatically creates bounded exact `P<number>` and `P<number>b` plate sides and records an audit event.
- Added the operator's current Cura Material Settings catalog, sanitized discovery of existing Cura materials, and explicit import into new draft profiles.
- Added material-only Cura rendering for all approved settings, including Cura Klipper Settings pressure advance and smooth time.
- Added versioned generic material templates scoped to a printer and nozzle, publication, and template provenance for copied product profiles.
- Added web workflows for creating templates and revisions, adding filament products from published templates, and adding physical spools without opening Spoolman.
- Added automatic Alembic upgrades before web and worker startup with a bounded PostgreSQL advisory lock and fail-closed error handling.
- Added authoritative full-library Cura synchronization, checksum-based drift repair, transactional cleanup/rollback of user material files, and a managed visibility plugin that hides bundled Cura materials.
- Added one-time adoption of existing Spoolman free-text spool locations and an in-app bucket/location editor.
- Added a case-insensitive remembered color library, real color swatches and pickers, and global propagation to every existing and future filament using the same color name.
- Added filament detail editing with every approved Cura Material Settings value, immutable profile revision history, and in-app draft creation and publication.
- Added complete physical build-plate editing for manufacturer, product, shape, dimensions, magnetic/flexible properties, condition, status, preferred materials, temperature limit, and notes.
- Added editable printer hardware details plus Administrator-controlled discovery of Klipper version, Moonraker version, hostname, kinematics, nozzle diameter, and build volume through documented APIs.
- Added the required Size and Hole Calibration step after Retraction, with server-side Horizontal Expansion and Hole Horizontal Expansion calculations and X/Y divergence warnings.

### Changed

- Changed Spoolman synchronization to queue each canonical mutation immediately and run a one-minute safety sweep that imports printer-recorded usage before converging every vendor, filament product, and spool.
- Changed the worker to honor its configured concurrent dispatcher count and reclaim abandoned running jobs after a bounded lock timeout.
- Kept P1-P5 as the initial physical set while allowing later plates and optional B sides to come from same-named saved Moonraker meshes.
- Changed selection, calibration context, dashboard state, and material preferences to record the exact plate side facing up.
- Changed Cura deployment to write one material file rather than quality-change profiles or machine start-G-code patches. The Material Settings and Klipper Settings plugins now consume the material values.
- Changed synchronization to align the selected printer's active physical plate and side with Moonraker while preserving existing physical and side metadata.
- Documented the hash-bound dry-run and commit procedure for importing the initial workbook with one-shot Swarm jobs.
- Changed new filament products to copy a published generic template into an independently tunable draft material profile.
- Changed Cura deployment from one selected profile to the latest published templates and product profiles as one desired-state library. Existing workstations with user materials require explicit Administrator takeover.
- Changed Compose and Swarm upgrades to migrate automatically; a one-shot migration remains only for diagnosis and recovery.
- Changed spool-location ownership so Filament Manager becomes authoritative after import, edit, or explicit clearing and repairs later Spoolman-side drift.
- Changed local username validation to allow two-character usernames and reduced the password minimum from 14 to 10 characters while retaining Argon2id hashing and the existing 256-character maximum.
- Changed calibration from six to seven ordered steps and made published calibration profiles inherit all settings from the selected starting profile before applying calibrated values.
- Changed profile editing to create a new independent draft version, preserving published profile and template revision immutability.
- Changed the workstation agent package version to 0.1.5 so current Arch Linux and Windows testing artifacts identify the matching server release.

### Fixed

- Fixed all filament and spool projections failing against Spoolman 0.23.1 because managed custom fields were undeclared and their values were not JSON-encoded.
- Fixed full reconciliation only reading existing remote spools instead of creating or repairing missing Spoolman vendors, filaments, and spools.
- Fixed metadata reconciliation potentially erasing unimported printer usage by writing canonical remaining weight during routine spool updates.
- Fixed failed, dead, and worker-crash-stranded Spoolman jobs remaining permanently stuck after the integration recovered.
- Fixed the initial `SELECT_BUILD_PLATE` macro state using an unambiguous Python literal so Klipper accepts the macro during startup.
- Fixed double-sided plates and different per-side meshes being impossible to represent.
- Fixed later physical plates being impossible to represent because the database column, JSON contracts, API client, macro, and interface were limited to P1-P5.
- Fixed lexicographic plate ordering that would place P10 before P2.
- Prevented missing Moonraker meshes from deleting or overwriting canonical physical-plate and side details; they are retained and shown as unavailable.
- Fixed web and worker replicas racing database upgrades or requiring the operator to pre-run every schema update.
- Fixed clean Cura installations requiring manual first synchronization and managed Cura material files drifting away from canonical Filament Manager state.
- Fixed routine product, spool, and generic-material setup requiring direct API or Spoolman access.
- Fixed the shipped build-plate macro default to use the explicit quoted `"UNSET"` string and documented how to locate stale included copies.
- Fixed filament color samples being isolated free-text values that could drift between products with the same named color.
- Fixed product-specific Cura settings, full build-plate metadata, and relevant printer information being visible only through limited API or database paths instead of editable application screens.
- Fixed calibration profile publication discarding unmodified settings inherited from a product's generic template.

## 0.1.4 - 08.11.2026

### Added

- Added an Administrator-only Printers page action that seeds the configured Moonraker printer and P1-P5 build plates from deployment environment variables.
- Added a shared idempotent first-run seed service for configured printers and P1-P5 build plates.

### Changed

- Changed browser workbook commit to auto-seed missing configured system records in the same transaction before importing printer-scoped material profiles.
- Changed the CLI `seed-system` command to use the same seed service as the web import flow.

### Fixed

- Fixed the Printers page empty state incorrectly telling Docker operators to edit a server-side YAML file.
- Fixed first-run browser workbook commits failing with `seed the configured printer before importing profiles` when the operator had not run the separate seed CLI command.

## 0.1.3 - 08.11.2026

### Added

- Added Administrator-only `.xlsx` workbook upload endpoints for dry-run validation, recent import run inspection, and explicit commit.
- Added a Settings workbook import panel that uploads the master workbook, shows validation totals and row findings, and commits a validated uploaded run.
- Added integration coverage for browser workbook upload, commit, audit recording, and projection outbox creation.

### Changed

- Changed workbook import reporting so uploaded runs retain the user-visible source filename while still committing only hash-verified stored bytes.
- Queued a Google inventory publication job after workbook import commits so the read-only publication target can rebuild from canonical state.
- Updated installation guidance to use the web import flow first and keep CLI import commands as a recovery path.

### Fixed

- Fixed the shared frontend request helper so multipart workbook uploads are not sent with a JSON content type.

## 0.1.2 - 08.11.2026

### Added

- Added regression tests for the trusted-host-aware web readiness probe and the non-HTTP worker health-check contract.

### Changed

- Changed the image readiness probe to connect over loopback while presenting the exact hostname from `FILAMENT_MANAGER_BASE_URL`.
- Disabled the inherited HTTP health check for worker and local one-shot services that do not listen on the web port.
- Updated one-shot Swarm migration, seed, and Administrator bootstrap commands to disable the image health check explicitly.

### Fixed

- Fixed Filament Manager web tasks being rejected as unhealthy when trusted-host middleware returned `400 Bad Request` to the old loopback-host probe.
- Fixed healthy worker tasks being replaced because they inherited a readiness probe for an HTTP server they do not run.

## 0.1.1 - 08.11.2026

### Added

- Added a root `docker-stack.yml` that deploys Filament Manager, its worker, and Spoolman together against remote PostgreSQL.
- Added a complete environment-only stack-variable contract for application URLs, one Moonraker printer, Google publication, operational tuning, credentials, and remote PostgreSQL.
- Added complete remote PostgreSQL provisioning, migration, stack deployment, seed, and first-user instructions.
- Added automated post-CI AMD64 and ARM64 GHCR publication with testing-oriented `latest` and immutable commit tags.

### Changed

- Made the combined remote-database stack the default production installation while retaining the independent stack files for operators who need separate application lifecycles.
- Expanded stack variables for remote database routing, scoped credentials, published endpoints, integration origins, one-printer settings, and operational tuning.
- Made independent-stack network and persistent-volume object names deployer-selectable variables.
- Changed Docker Compose and Swarm deployments to use ordinary environment variables instead of Docker secrets for the current testing phase.
- Added masked inline credential support for the canonical database, Moonraker, Google publication, and the one-shot Administrator bootstrap.
- Documented how existing deployments can preserve current credential values during the variable migration and remove obsolete Docker secret objects only after verification.
- Removed the external Docker-config prerequisite; Docker services now build their complete validated configuration directly from environment variables.
- Limited the current Docker deployment contract to one Moonraker printer and made it derive the WebSocket URL from the HTTP URL when no override is supplied.
- Changed the canonical database role to `filament_user` and made both PostgreSQL clients explicitly disable TLS for the isolated database network.

### Fixed

- Corrected the Swarm instructions to explicitly export `.env` values because `docker stack deploy` does not load `.env` automatically.
- Used Spoolman's supported async PostgreSQL query syntax for explicit non-SSL connections and removed an unsupported allowed-host variable that could imply protection the pinned image does not provide.
- Removed obsolete Docker secret mounts and the local secret-copy entrypoint so every current Docker deployment path follows the stack-variable contract.
- Removed baked example hostnames and printer details from the active Docker configuration path.
- Corrected workstation pairing configuration construction and included the audit tool in agent development dependencies so strict CI runs through completion.

## 0.1.0 - 08.05.2026

### Added

- Complete FastAPI, React, and PostgreSQL Filament Manager application with local Administrator, Operator, and Viewer accounts.
- Canonical inventory, immutable physical measurements and usage, material profiles, the exact six-step calibration workflow, printers, and P1-P5 build plates.
- Hash-bound workbook dry-run and commit import, QR spool labels, append-only audit history, transactional outbox, and scheduled reconciliation workers.
- Supported Spoolman REST, Moonraker, Google Sheets publication, local Docker Compose, independent production Swarm stacks, migrations, health checks, metrics, and operational documentation.
- Workshop Navy light and dark design system, responsive printer-side weighing flow, automated backend/frontend tests, and rendered validation references.
- Cross-platform Cura workstation agent for Arch Linux and Windows 11 with one-time pairing, automatic Cura/machine discovery, outbound-only deployment polling, complete material and quality profile rendering, guarded pressure-advance injection, automatic backup, atomic writes, checksums, and rollback.
- Cura workstation management and deployment history UI, one-click deployment to every active agent, hardened systemd user and Windows logon-task installers, standalone binary build workflow, API lifecycle tests, and isolated local-agent tests.

### Changed

- Standardized the product and all technical identifiers on Filament Manager.
- Made PostgreSQL authoritative while preserving standalone Spoolman as the printer-facing operational service and the workbook as an initial-import fixture.
- Adapted the approved Workshop Navy palette into consistent light and dark application themes.
- Replaced the frontend routing dependency with a small same-origin History API router after dependency review.
- Changed Cura profile delivery from download-only JSON to optional automated, agent-scoped deployment while retaining manual export.

### Fixed

- Preserved the corrected `P11-S` workbook identifier so every imported physical spool code is unique.
- Made the initial migration fully reversible, preserved unknown Spoolman extension fields, and established an unknown tare atomically with its first measurement.
- Raised the development test-tool floor to the patched Pytest 9 release identified by dependency audit.
- Removed package-manager and build tooling from the non-root production image after runtime dependency audit.
- Separated local PostgreSQL administrator, canonical application, and Spoolman roles and limited the bootstrap password to its one-shot Compose service.
- Preserved restrictive host secret permissions during local PostgreSQL initialization through an ephemeral privilege-drop handoff.
- Prevented Cura writes while Cura is running, path escapes and symlink traversal, ambiguous machine targeting, unbounded agent metadata, credential replay, and unsafe replacement of unknown inherited start G-code.
