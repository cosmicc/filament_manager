# User Changelog

## 0.8.2 - 09.09.2026

Testing release.

### Added

- Printer settings now refresh current hardware values automatically when a save conflict occurs.

### Changed

- Reworded filament-related selection labels from **Filament product** to **Material template** in print settings and material-scoped actions.

### Fixed

- Fixed save conflicts when updating printer max extruder/bed limits so stale edits no longer fail with “Printer changed; reload.”

## 0.8.1 - 09.08.2026

Testing release.

### Added

- Spool type selection and reusable New Spool Type choices. Empty-spool weight suggestions now match manufacturer, type and filament capacity.
- Last completed and last cancelled/failed print dates on inventory and printer details.
- Printer total printing time and longest print from Moonraker, with the last successful update date.

### Changed

- Pressure Advance replaces the Klipper settings heading. Filament density follows its template silently.
- Numbers display at most two decimal places without reducing saved precision.
- Print History shows Cura profile used separately from the machine.

### Fixed

- Missing history settings can display the print's saved app values, clearly distinguished from recorded G-code evidence. Unknown past values remain unknown.

## 0.8.0 - 09.08.2026

Testing release. Multi-hotend loading requires reviewed printer macros and explicit routine verification in printer settings.

### Added

- Guided Google setup in Settings, app-managed printer connections, heated-chamber and temperature-limit details.
- Dashboard printer switching, an all-printers overview, and Sync to Cura.
- Optional printer-macro support for acknowledging print removal and displaying the idle power-off countdown.
- Separate loaded spools for independent hotends, automatic permanent spool codes, remaining-filament bars in Locations, and a Cancel/Override warning before a print with insufficient filament.

### Changed

- Dashboard printer context stays together and inventory totals move to the bottom.
- Density appears beside template diameter; Ironing follows Dimensional compensation in template and filament settings.
- Filament list names are bold above their smaller manufacturer name. Confirmed printer power-off is shown separately from printer errors.

### Fixed

- The supplied QQ-S macro file now remembers the original pause position, parks safely, and returns above the print before lowering and resuming. User, runout and slicer pauses share this behavior, with safety exceptions near maximum height and before homing.

- Printer actions stay with the selected printer instead of silently using the first one.
- A spool must be unloaded from its current printer before it can be loaded on another.
- The separately prepared custom macro update corrects the automatic countdown while retaining the 60-minute reset.

## 0.7.9 - 09.07.2026

Testing release. Upgrade the app and worker, then follow the Google setup guide linked in Settings. No new Klipper macros are needed from 0.7.8.

### Added

- Connect Google and Sync now in Settings, creating a Filament Manager spreadsheet in your Drive.
- Linked, filterable tables for inventory, settings, templates, calibration, build plates, nozzles and print history, including archived records and the settings captured for each print.
- A workbook Dashboard with counts, remaining filament and a material chart, coordinated colors and easy navigation.

### Changed

- App changes publish automatically in grouped background updates. Publishing waits during prints; the app remains the only source of truth.

### Fixed

- Google setup is available again, and publication includes much more than the old spool inventory tab. Sync errors are shown without exposing credentials.

## 0.7.8 - 09.07.2026

Testing release. Upgrade the app and workstation agent; close Cura, use **Push app settings**, wait for **Succeeded**, then reopen Cura and re-slice/upload the tower.

### Added

- Automatic Cura-side correction for the recognized AutoTowers retraction-speed tower base.

### Changed

- After installing the updated workstation agent, synchronize with Cura closed, reopen Cura, and re-slice/export the tower. Existing uploaded files are not repaired.

### Fixed

- Prevent AutoTowers from replacing valid base retract/prime speeds with zero or negative speeds. The tower's actual calibration speeds and your **Warn and continue** inspection choice remain unchanged.

## 0.7.7 - 09.07.2026

### Added

- Automatic replacement of the affected Cura plugin after upgrading the workstation agent and synchronizing with Cura closed.

### Changed

- Filament Manager continues to control tracked print settings. Cura edits still revert to the app's values, and your templates and custom filament settings are preserved.

### Fixed

- Fixed valid material print settings turning red and preventing slicing after recent updates. Cura now receives numbers and on/off values in the format its validation system expects.

Upgrade the app and workstation agent to 0.7.7. Close Cura, select **Push app settings**, wait for **Succeeded**, then reopen Cura. No new Klipper macro installation is needed when upgrading from 0.7.6.

## 0.7.6 - 09.07.2026

### Added

- Cura synchronization now refreshes plugin enforcement safely on the active machine profile instead of forcing unsupported settings.

### Changed

- Push app settings now keeps managed Cura plugins aligned to the current machine's visible Material Settings keys, so valid configurations no longer show red overrides when slicing.

### Fixed

- Managed print settings that are supported by the active machine no longer appear invalid after recent one-way Cura updates.
- Stationary settings now stay writable only from Filament Manager, and Cura now receives refreshed plugin behavior from the latest closed-Cura app update.

## 0.7.5 - 09.07.2026

### Added

- Automatic retraction window matching and a fixed maximum retraction count of 100, shown read-only in templates.

- **Push app settings** on Cura Workstations sends the latest app values. Close Cura and wait for synchronization to succeed before reopening.

- Plate, nozzle, and active-spool changes are locked during printing and pauses; deliberate M600/runout filament replacement remains available.

- Customize drying temperature, drying time, and moisture sensitivity in each filament's print settings, or use Revert to Template.

### Changed

- Care values still inherit from templates unless customized; custom values remain when the template changes.

### Fixed

- Cura can no longer change app print settings. Edit values in Filament Manager; app customizations and history remain intact. Update both server and workstation agent.

- Removed the template-only message under filament and spool drying guidance.

## 0.7.4 - 09.07.2026

Testing release.

### Added

- Successful idle loads of exact P-number Klipper meshes update the app-selected build plate side without recording a calibration.

### Changed

- Filament diameter inputs and details use at most two decimal places.
- Missing and unspecified manufacturers consolidate under Unknown, including archived filaments, without changing print history.
- Filaments with matching names remain separate, with their original spools and print history preserved.
- Spoolman filament defaults use the most common positive empty-spool weight for each manufacturer and filament capacity, including archived evidence. Individual spool tare weights remain unchanged; Unknown manufacturers are not pooled.

### Fixed

- Build-plate selection confirms live printer/probe state and saved mesh availability instead of remaining blocked by an old in-progress print record.
- Stale print records no longer indefinitely prevent idle background printer synchronization; unreachable or unknown printer state remains safely blocked.



## 0.7.3 - 09.07.2026

Testing release.

### Added

- Moisture sensitivity and drying time in material templates, shown with drying temperature in linked filament and spool details.
- Print History shows whether the saved print settings still match the current template and highlights changed values without altering the original record.
- Last printed and last activated dates for every build plate and side.
- Automatic recording of successful side heightmap calibrations with the updated printer macros.
- Automatic restoration of the selected heightmap at printer startup, without a chooser.

### Changed

- Printers is now 3D Printers. The Calibration menu opens the Filament Calibration page.
- Template cards now show drying temperature and time; filament cards show drying temperature instead of tolerance.
- Removed plate cleaning tracking, reminders, history, and the maintenance ledger.
- Use `SELECT_BUILD_PLATE CHOOSE=1` if you want to open the printer-side chooser manually.

### Fixed

- Restarting Klipper no longer forgets the app's selected build plate. Missing meshes block managed print start instead of selecting another plate.
- Loading an existing heightmap no longer needs a manual calibration button and is never counted as a new calibration.

## 0.7.2 - 09.06.2026

Testing release.

### Added

- Easier-to-see print thumbnails in Print History and on the Dashboard, with automatic contrasting backgrounds for dark, light, and mixed-color models.
- A coordinated fourth accent for every theme, used in section headings and summary details.
- A visible New Color button beside the filament color list.
- Six compact dashboard buttons: Weigh spool, Build plate, Calibrate, Add filament, Add spool, and Load spool.
- Smaller inventory cards showing spool totals, weighing needs, low/empty stock, counts by material type, and how many named colors you own.

### Changed

- Color, filler, and finish lists contain choices used by current or archived filaments. New choices are saved only when you save the filament; cancelling leaves no unused entries.
- Dashboard actions now live together in the header instead of a separate Quick actions card.
- Filament colors can be corrected after use; all linked spools update automatically.

### Fixed

- Dark previews with a built-in background get a display-only contrast boost where the image contains recoverable detail. Original thumbnails and print history stay unchanged.
- None finishes now become Standard, while filler keeps None as its default.
- You can correct all two or three colors of a multicolor filament without changing previous print history.
- Correcting a color preserves previous print-history colors and settings, spool IDs, and recorded weights.

## 0.7.1 - 09.05.2026

Testing release.

### Added

- Set **Filament drying temperature** in a template's temperature section and view it in filament/spool details. It cannot be changed on individual filaments and does not control printer heaters.
- Spool **Location** is a dropdown of remembered locations. Choose **New Location** at the bottom to add one without losing your spool form; **Unassigned** clears the location.
- Add saved colors, manufacturers, fillers, and finishes using the last **New [Item]** choice in their dropdowns. A new color includes its display color.
- Change a filament's print-settings template while keeping custom values and using the new template's inherited defaults. Past prints remain unchanged.
- Browse **Locations** to see each storage location and open the spools kept there, including unassigned or optionally archived spools.
- Filter Filaments and Spools by template-derived filament type, with **All** selected initially.
- View a read-only **Current total spool weight** and choose remembered empty-spool weights from the same manufacturer.

### Changed

- Filament details now say **Manufacturer**. Empty fillers become **None** and empty finishes become **Standard**, without adding those words to filament or spool names.
- The spool location field is now simply **Location**, with **Bucket 12** as its example.
- Changing empty-spool tare now updates remaining filament automatically from the last total scale weight while preserving subsequent usage. Spools without a weigh-in retain their existing estimate.
- New-spool entry distinguishes unused spools, whose tare can be inferred, from used spools that need an entered or suggested tare.

### Fixed

- Fixed a red save error after a spool was actually created, including full-weight entry. A background refresh failure no longer makes a successful save look unsuccessful.
- Corrected stale remaining weights after tare changes without altering original weigh-in history.
- Prevented old Spoolman balances and unchanged rounded form values from undoing weight corrections.
- Fixed saving spools linked to a manufacturer.

## 0.7.0 - 09.04.2026

### Added

- Print History now remembers complete managed and safely embedded Cura settings for new prints, including which values differed from the filament template, and shows them in **Advanced print settings**.
- After creating a filament, Filament Manager now asks whether to create its first spool and preselects that filament when accepted.
- Added **Create spool from filament** while viewing an active filament.

### Changed

- Filament and spool searches now include filler and finish.
- Filament names are now automatic from type, color, filler, and finish, with no editable Display name. Blank, `None`, and `Standard` modifiers stay out of filament and spool names, including Spoolman and Cura.
- Updated Filament Manager and its workstation agent to version 0.7.0.

### Fixed

- Spoolman now receives filament price, empty-spool weight, and the installed-nozzle profile's extruder and bed temperatures. Each spool keeps its own purchase price and empty weight; shared pricing stays blank when spool currencies differ.
- Fixed template-matching values, including initial build-plate temperature, remaining marked as custom after save.
- Fixed a false custom-setting count when every displayed print setting was inherited.

## 0.6.7 - 08.31.2026

### Added

- Added clearer backup failure guidance so a failed attempt explains the safe next action in Diagnostics.

### Changed

- Moved Print History directly below Printers, renamed the Cura workstation action to **Add Cura workstation**, and removed Logout from the bottom of the sidebar.
- Cleaned up the automatic-backup schedule controls into a compact enable, frequency, retention, and save group.
- Changed live printer refreshes from five to ten seconds and reduced Moonraker work during an active print.
- Updated Filament Manager and its workstation agent to version 0.6.7.

### Fixed

- Fixed automatic and manual backups remaining unavailable after an interrupted print left stale in-progress history.
- Fixed backup storage failures hiding the original useful error or retrying too aggressively.
- Reduced avoidable Moonraker, Klipper, and Fluidd activity during printing by combining the essential live query and postponing nonessential synchronization until the print ends.

## 0.6.6 - 08.30.2026

### Added

- Added four dark themes: Deep Ocean, Carbon Lime, Ember Red, and Arctic Slate.
- Added an **Add Build Plate** action that creates the next P-number with Side A ready for later mesh discovery.
- Added printer filters to Print History and Nozzles, and a one-day, seven-day, or thirty-day Recent errors filter to Diagnostics.

### Changed

- Active browser pages now remain signed in for multiple days, up to the thirty-day absolute session limit.
- While printing, the Dashboard gives more room to printer progress and uses smaller temperature cards.
- Completed, cancelled, and failed Print History entries now have subtle green, yellow, and red backgrounds.
- Moved the Filaments Catalog/Print settings selector beside the main page action and removed the redundant Integrations page.
- Updated Filament Manager and its workstation agent to version 0.6.6.

### Fixed

- Fixed automatic and manual PostgreSQL backup compatibility, improved the displayed failure reason, and stopped failed automatic backups from retrying every minute.
- Reduced printer-host load during active prints by postponing database backups, avoiding repeated full-history downloads, and stopping a stuck print-resume retry after thirty seconds with clear Retry and Cancel choices.
- Build plates without a matching Klipper heatmap profile now show an obvious warning instead of appearing ready.

## 0.6.5 - 08.29.2026

### Added

- `FILAMENT_MANAGER_SPOOL_STATE` now reports the active Klipper macro version so an outdated installed copy is easy to identify.

### Changed

- Updated Filament Manager and its workstation agent to version 0.6.5.

### Fixed

- Fixed **Cancel Print** doing nothing after a print stopped at the purge line, leaving Klipper stuck in printing state and Fluidd's printer power control unavailable.

## 0.6.4 - 08.29.2026

### Added

- Added automatic recovery coverage for interrupted G-code inspection acknowledgements.

### Changed

- Blocking G-code inspection now safely retries its completed decision while Fluidd is still waiting.

### Fixed

- Fixed prints remaining stuck on Fluidd's **Inspecting G-code** dialog with only **Cancel Print** available.

## 0.6.3 - 08.28.2026

### Added

- Print History now shows a clear retry option when its request fails instead of incorrectly saying there are no print records.

### Changed

- The Dashboard now starts with the printer status card, places the three inventory value cards directly beneath it, and no longer shows the extra description below the page title.
- Cura material names no longer display a filler when it is empty or set to `None`; meaningful fillers such as Carbon Fiber remain in the name.

### Fixed

- The notification panel now closes when you click outside it.
- Fixed existing prints disappearing from Print History after the 0.6.2 pagination update.
- Fixed Dashboard print status and progress overlapping when the current print has no thumbnail.
- Fixed prints completing the purge line and then remaining paused at 0%; Filament Manager now safely releases its own virtual-SD hold without interfering with a normal Klipper pause.
- Cancelling during print inspection or spool selection now cancels the held file, and selecting a required build plate correctly finishes the printer start sequence.

## 0.6.2 - 08.28.2026

### Added

- Print History now has 10, 25, 50, and 100 records-per-page choices plus First, Previous, Next, and Last navigation; 10 records is the default.

### Changed

- Print History now shows Moonraker's last known outcome, including printer shutdown, disconnection, interruption, cancellation, and error states.
- Managed Cura start G-code now carries separate initial-layer and regular build-plate temperatures for exact inspection.

### Fixed

- Fixed blocked or interrupted prints remaining labelled as in progress or unknown after Moonraker recorded a final outcome.
- Fixed valid prints being blocked because Cura's saved quality-profile bed temperature was incorrectly treated as the resolved managed material value.
- Fixed Cura keeping a stale extruder nozzle diameter until the physical nozzle changed again; the workstation agent now verifies it during every check-in and queues a repair when needed.

## 0.6.1 - 08.28.2026

### Added

- Added validation coverage for profiles that intentionally use different regular and initial-layer build-plate temperatures.

### Changed

- Managed Cura product names now include a non-empty filament filler, clearly distinguishing entries such as `SUNLU Black Carbon Fiber` from `SUNLU Black`.

### Fixed

- G-code inspection now keeps initial-layer and regular build-plate temperatures separate, preventing valid prints with different values from being falsely blocked.

## 0.6.0 - 08.27.2026

### Added

- Filament Manager now automatically saves and maintains the required start and end G-code in the matched Cura printer configuration.
- Diagnostics can now schedule compressed database backups, retain the newest automatic snapshots, download or import trusted backup ZIPs, and prepare a controlled catastrophic restore.

### Changed

- The Dashboard now refreshes printer status, active spool, active build plate, and inventory values every 5 seconds and refreshes immediately after reconnecting or returning to the page.
- Nozzle changes now also verify that Cura still has the Filament Manager start and end scripts.
- Diagnostics no longer shows the Projection operations / Recent jobs table.

### Fixed

- Fixed Cura's saved printer scripts not showing the required `FILAMENT_MANAGER_START_PRINT` inspection call.
- Fixed operational Dashboard values taking up to 15 seconds to reflect a printer, spool, or plate change.
- Fixed a Cura plugin recursion that could prevent Cura from opening and rapidly repeat crashes until the workstation became unstable.

## 0.5.8 - 08.26.2026

### Added

- Added validation that the Filament Manager load and unload commands use the printer's preserved physical movement routines.

### Changed

- Klipper setup now gives the printer's physical load and unload routines stable internal names while Filament Manager owns the public commands.
- The login content now starts at the top of the page with compact spacing below the Filament Manager brand.
- Print History now explains that the Filament Manager inspection call comes from Cura's sliced start sequence before the printer's unchanged `START_PRINT` macro.
- Customized filament values now have a prominent warning highlight and a **Revert to Template** button that removes the custom value when saved.

### Fixed

- Fixed Klipper refusing to start because `UNLOAD_FILAMENT` or `LOAD_FILAMENT` did not exist for the app macro file to rename.
- Fixed managed Cura slices retaining the printer's saved start/end scripts instead of receiving the Filament Manager inspection boundary automatically.
- Fixed template changes appearing not to reach linked filaments because their inherited settings stayed cached; non-customized values now refresh immediately and customized values remain unchanged.

## 0.5.7 - 08.26.2026

### Added

- Material templates and filament settings now have a separate Initial Layer Build Plate Temperature that synchronizes with Cura.
- The Dashboard and Print History now show stored print thumbnails when Moonraker provides them.
- Current and past prints now show useful time and filament comparisons plus actual filament cost when purchase pricing is available.

### Changed

- Filament Manager material settings stay authoritative in Cura without being added to the custom quality profile you are editing or saving.
- Managed material-setting edits made in Cura still save back to Filament Manager and synchronize to the other managed Cura installations.
- Managed Cura materials now use the required Filament Manager start and end print macros automatically without changing your saved machine scripts.
- Cura recovery keeps the latest 15 automatic backups, while named backups stay until you delete them.
- Clicking a template row or card now opens its editor; Export JSON and Delete are available inside that editor.

### Fixed

- Fixed Cura custom quality profiles trying to save Filament Manager's material settings as part of the quality profile.
- Fixed Klipper refusing to start because the Filament Manager M600 macro tried to rename an M600 command that did not exist.
- Fixed managed prints missing the Filament Manager inspection gate and exact material-profile match.
- Fixed initial-layer bed temperature being unable to differ from the regular build-plate temperature.

## 0.5.6 - 08.26.2026

### Added

- The login page now shows the running Filament Manager version.
- Material templates can be deleted after typing the exact template name; history remains safely retained.
- Existing templates can change their printer and physical nozzle association.

### Changed

- New templates now default to the currently installed nozzle when one is available.
- A blocked G-code result now explains whether the printer-side inspection gate was actually active.

### Fixed

- Fixed Cura reporting managed materials and extruder profiles as corrupt after a material settings edit.
- Fixed current managed G-code losing its exact material-profile match after later profile revisions.

## 0.5.5 - 08.26.2026

### Added

- Filament product save errors now highlight the exact rejected field, explain the reason, and move focus to it.

### Changed

- Detailed template cards now use their available width without unnecessary title or fact truncation.
- Template cards show material Flow instead of the identical number of managed settings.
- Filament cards now show tolerance and printing temperature instead of diameter and nominal spool weight.
- Filament and spool titles omit filler when it is `None` and finish when it is `Standard`.

### Fixed

- Fixed clearing a Rainbow filament's optional display name failing because its fixed six-color display palette was submitted as a user-defined multicolor palette.
- Fixed a failed named Cura backup request temporarily appearing as a current Cura-agent failure after the agent itself had recovered.

## 0.5.4 - 08.25.2026

### Added

- Material templates now have List, Cards, and Detailed views.
- Templates can be downloaded as JSON and imported to create a new material template or replace one explicitly selected template after confirmation.
- PEBA, ABS, and PP are included in the common material suggestions.

### Changed

- Mouse-wheel scrolling no longer changes a focused numeric field.
- Template creation from existing Cura sources remains part of Cura workstation takeover instead of a separate Templates-page shortcut.

### Fixed

- Fixed selecting Rainbow making all filaments disappear from the interface and making print settings show `Unknown filament`; the underlying filament and template work was not deleted and becomes visible again after upgrading.
- Filament edits now fail safely before saving if the server cannot return the edited product correctly.

## 0.5.3 - 08.25.2026

### Added

- Filament and spool identities now prominently show Type, Color, Filler, and Finish together.

### Changed

- Every cooling setting can now be customized for an individual filament profile while still inheriting its template value until changed.
- Regular and Maximum Fan Speed now allow 0%; Regular Fan Speed at Layer starts at 1.

### Fixed

- Fixed filament profiles showing only one of the available cooling controls.
- Fixed spool and filament cards omitting important filler or finish information from their main identity.
- Fixed a Cura backup capture warning incorrectly making the entire connected workstation agent appear unhealthy.

## 0.5.2 - 08.25.2026

### Added

- Save errors now list every rejected field and reason; unexpected failures include a safe reference that matches Diagnostics and application logs.
- Every blank template value now visibly offers **Copy from another template** and explains when no other active template has that value.

### Changed

- Template cards now keep long printer, nozzle, and settings text inside their card boundaries.

### Fixed

- Fixed valid ironing flow, speed, and line-spacing values failing a template save when a Cura workstation was paired.
- Fixed template and filament print-settings validation falling back to an unhelpful general rejection.
- Fixed blank template values hiding the copy option instead of showing the available source templates.

## 0.5.1 - 08.25.2026

### Added

- Windows workstation installation now pairs interactively, makes `filament-manager-agent` available in new terminals, starts immediately, and runs automatically at sign-in.
- A fresh Cura installation can restore a reviewed, exact-version backup from another paired workstation before Filament Manager synchronizes the current nozzle and material library.
- Blank template settings now offer a **Copy from** list containing every active template that has a value for that setting.
- Every nozzle now belongs to a specific printer, and every template identifies the exact printer and physical nozzle it controls.

### Changed

- Cura quality profiles now control whether ironing is enabled. Filament Manager continues tracking ironing flow, speed, and line spacing for each material.
- Cura Workstations now verifies 53 managed Material Settings instead of 54.
- Template cards now put the printer beneath the title, show exact nozzle details, and omit repetitive stored descriptions.
- Spool, Filament, Build Plate, and Nozzle cards remain equal in size within each view and truncate unusually long text. Filament and Nozzle list rows open directly when clicked.

### Fixed

- Improved invalid template-setting feedback so the exact rejected control is visibly marked and focused instead of leaving only a generic save failure.
- Prevented templates for different physical nozzles from being treated as the same diameter-only scope.

## 0.5.0 - 08.25.2026

### Added

- Added **Catalog** and **Print settings** navigation under Filaments.
- Added a print-settings view that clearly lists every filament's current printer and nozzle combinations.
- Added an action on filament details to create another printer/nozzle print-settings configuration from a compatible template.

### Changed

- Filament details now keep product information separate from printer/nozzle print settings, with Edit, Compare, and Cura JSON export actions on each exact configuration.
- The former Profiles page is now **Filaments → Print settings**; saved `/profiles` links continue to work through an automatic redirect.
- The Dashboard printer status pill is substantially larger and easier to read without making its card larger.

### Fixed

- Fixed template, density, duplication, and editing changes selecting the wrong print settings when one filament has multiple printer or nozzle configurations.
- Fixed inactive-template changes occasionally failing because the saved template could not be read back safely.

## 0.4.3 - 08.25.2026

### Added

- Added clear History labels to retained Diagnostics failures that no longer represent current health.

### Changed

- Recovery points now lists saved Cura configurations before recent backup requests.
- A saved validation now shows every check counted by its error and warning totals, while the live sections below continue showing current health.

### Fixed

- Fixed failed Cura backup requests appearing as several active Cura synchronization errors.
- Fixed generic Cura synchronization notifications duplicating the detailed failure already retained in Diagnostics.

## 0.4.2 - 08.24.2026

### Added

- Added a modern login page featuring a rendered delta 3D printer and filament spools with concise, formal product wording.
- Added the ability to change tracked values on an existing managed Cura template or filament material and save them back to Filament Manager automatically.

### Changed

- Filament Manager now adds its 54 required Material Settings choices while preserving unrelated choices you enabled in Cura.

### Fixed

- Fixed Cura asking for the obsolete `ironing_speed` setting; Cura 5.13 now receives and verifies `speed_ironing`.
- Fixed the removed **Limit Support Retractions** setting remaining in Cura Workstations because a failed backup upload prevented the agent from installing the corrected library.
- Fixed a failed Cura backup upload blocking all later material, nozzle, and restore synchronization work.
- Fixed tracked Cura values snapping back before they could be saved.

## 0.4.1 - 08.24.2026

### Added

- Added automatic cleanup of previously managed **Limit Support Retractions** values during the next Cura material-library synchronization.
- Added a large live printer card to Dashboard showing whether Moonraker and Klipper are available, the current idle/printing/paused/finished state, print progress and filename, and available nozzle, bed, and chamber temperatures.

### Changed

- Removed **Limit Support Retractions** everywhere in Filament Manager and from the required Cura Material Settings list.

### Fixed

- Fixed the List/Cards/Detailed menu and its choices appearing white-on-white when using a dark color profile.
- Fixed automatic and manual Cura backups failing on valid Cura setting-visibility files and improved the safe failure reason shown when a different Cura settings file cannot be captured.

## 0.4.0 - 08.24.2026

### Added

- Added automatic scrolling and focus to the exact template setting that needs correction.
- Added **List**, **Cards**, and **Detailed** view choices to Spools, Filaments, Build Plates, and Nozzles. Each page remembers its own choice in the browser.

### Changed

- Build Plates now uses compact responsive cards with smaller plate summaries, denser facts, neatly grouped sides, and desktop buttons sized to their labels instead of stretched across the page.
- Spools now fills the available page width instead of reserving space for a selection card. Select any spool to open its full details and actions.
- Page headers, cards, toolbars, tables, empty states, and repeated record grids now use space more efficiently across the app while preserving all existing information and mobile touch sizing.
- Build-plate editing now shows width and depth only for rectangular plates and diameter only for round plates. The unused **Other** shape option was removed.
- Opening a template editor now refreshes that template first so its version and values are current.

### Fixed

- Fixed shared action buttons on several pages expanding to the full width of their container on desktop.
- Fixed rejected template values being difficult to locate in the long settings editor. The exact setting is now strongly highlighted in red with its reason beside it.
- Fixed a genuine simultaneous template update using the vague **Template changed; reload and retry** message without explaining what happened.

## 0.3.3 - 08.22.2026

### Added

- Added a Material Print Settings status to every managed Cura installation showing the exact verified count, required plugin versions/readiness, missing settings, and last verification time; the same result appears in Diagnostics.
- Added automatic database upgrade support for the larger identifiers used by manually requested synchronization jobs.
- Added template-only Print, Infill, Wall, Top Surface Skin, Top/Bottom, Support, and Travel Acceleration settings. Cura acceleration control and travel acceleration are always enabled automatically.
- Added complete safe Cura printer/extruder setting backup coverage, including start/end G-code.
- Added ironing settings to both templates and filament profiles.
- Added live progress and useful sanitized error feedback for named Cura backups.

### Changed

- Filament Manager now automatically restores the required 55-setting Material Settings plugin selection when it drifts and verifies those settings after Cura starts.
- Print speed settings and cooling settings other than Initial Fan Speed now live on templates and automatically flow to linked filament profiles.
- Pressure advance and Initial Fan Speed are editable on both templates and filament profiles. Smooth time and acceleration remain template-only.
- Flow is now one primary setting, and the temperature editor now uses only Printing Temperature, Build Volume Temperature, and Build Plate Temperature.

### Fixed

- Fixed a missing, disabled, or incompatible Cura settings plugin appearing healthy simply because the material files synchronized successfully.
- Fixed a managed Cura edit being able to fail the workstation heartbeat when a customized filament fan value crossed a changed template fan value.
- Fixed **Queue Spoolman reconciliation** and related manual projection actions failing before their jobs reached the worker.
- Fixed nozzle changes updating the wrong Cura stack; the linked extruder nozzle size is now aligned again after a Cura restore.
- Fixed repeated Spoolman weight corrections staying pending until they died in the Projection Queue.
- Fixed an already-recovered manual Moonraker synchronization remaining forever as one dead Projection Queue item.
- Fixed named Cura backups after a reset producing no saved point and no useful feedback.
- Fixed old Cura synchronization failures staying active after the current full library had synchronized successfully.

## 0.3.2 - 08.21.2026

### Added

- Added **Duplicate** on filament details to start a new filament with copied product data, template, and customized settings without copying physical inventory or history.
- Added on-demand named full Cura backups, optional descriptions, editable backup details, and confirmed deletion that keeps an unchanged automatic recovery point from immediately reappearing.
- Added exact nozzle details, more slicer/job timing and filament-use information, and secure timelapse video links to completed Print History records.
- Added automatic Cura nozzle-variant selection after installing a different physical nozzle when Cura already has one exact matching variant.
- Added purchase weight, purchase cost, and calculated cost per gram to physical spools. Cura receives a weighted cost for each managed product material when its available priced spools use one currency.
- Added a Diagnostics summary showing the latest sanitized cause for every currently failing projection type.

### Changed

- Customized filament settings now have a stronger visual accent while retaining the Inherited/Customized explanation and Reset to Template action.
- Cura Workstations now reports the managed material library separately from pre-takeover sources and user-saved custom print profiles, making a legitimate zero custom-profile count clearer.
- Full Cura recovery now retains safe Cura2Moonraker upload, start, output, transformation, camera, and power-device choices while keeping connection URLs and API keys local.
- Projection scheduling now keeps only the current recurring attempt actionable. The upgrade automatically retires obsolete recurring/metadata failures and retries unfinished Spoolman weight work.

### Fixed

- Fixed repeated spool-preflight catalog errors creating growing dead-job totals and repeated warning entries. The catalog problem now appears as its own actionable Diagnostics check without stopping the rest of Moonraker state synchronization.
- Fixed Print History hiding the exact physical nozzle and showing an internal G-code SHA-256 value instead of more useful print details.
- Fixed synchronized Cura material counts appearing as zero because only unmanaged pre-takeover files were counted.
- Fixed recovered projection history continuing to inflate the dead count and fixed one repeating error from hiding the cause of other failing projection types.

## 0.3.1 - 08.20.2026

### Added

- Added optional Bugsnag error monitoring for the browser, application server, and worker, plus optional browser performance monitoring.
- Added a clear reload screen when an unexpected browser rendering failure prevents the normal interface from opening.

### Changed

- Monitoring is disabled by default and can be enabled through deployment variables. Reports remove private URLs, submitted values, credentials, user identity, hostnames, and raw error messages before leaving Filament Manager.
- Browser performance reports use normalized routes and ignore frequent background polling so the dashboard focuses on meaningful navigation and application work.

### Fixed

- Fixed unexpected browser, server, and terminal worker failures being visible only through local logs.
- Fixed repeat worker failures being able to create excessive duplicate external reports.

## 0.3.0 - 08.20.2026

### Added

- Added separate Retraction Retract Speed and Retraction Prime Speed values and the requested five Cooling settings for every filament and template. Initial Fan Speed is always zero without adding another visible option.
- Added a final calibration-results review that can apply recommendations to the filament or, after a strong confirmation, to its linked material template. Unapplied calibrations can now be deleted with confirmation.
- Added build-plate picture uploads, editable nozzle codes, and a visual highlight on the currently installed nozzle.
- Added three light and five dark GUI color profiles in Settings, clearer color-coded Activity cards, and full-width horizontal Dashboard Quick Actions with Select Filament and Add Filament.
- Added one Account editor for changing the Administrator username, display name, and password.

### Changed

- New installations now use `admin` / `admin` and require the password to be changed on first login. Existing single-account credentials are retained, and Docker account variables are no longer used.
- Rainbow is now a filament color. Multicolor filaments can use one, two, or three individual colors, and each multicolor filament keeps its own spool palette.
- Downloading Cura settings now saves a JSON file. QR labels use a larger centered colored spool icon while remaining scannable.
- Dashboard and Integrations no longer duplicate Diagnostics information, and the Settings Security Defaults card was removed.

### Fixed

- Fixed Diagnostics reporting 1,125 old recurring jobs as dead even after later runs recovered; recovered history no longer counts as active queue debt.
- Fixed completed prints warning that no exact managed material profile could be resolved when their G-code contained a valid Filament Manager material ID.
- Fixed the filament color selector not reopening its list when choosing a different known color.
- Fixed a Cura prime-speed edit being able to clear the independently tracked retraction retract speed.

## 0.2.6 - 08.19.2026

### Added

- Added a reusable full-color 128 x 128 Filament Manager icon for Pushover and other notification services.

### Changed

- Spool QR labels now place each filament's colored spool icon in the center of the code, including solid, multicolor, and rainbow palettes.

### Fixed

- Fixed the label preview showing a color badge that was missing from the saved and printed QR image.

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
