# Printing Workflow

## Recommended policy

Use **Warn and continue** under **Settings → G-code inspection policy** while testing 0.6.2. Filament Manager still records every mismatch in Print History. Change the setting to **Block mismatches** after the Cura material library, printer macros, and first exact-state records have been verified.

Blocking pauses virtual-SD execution in Fluidd until Filament Manager can resolve the managed material profile, safely inspect the G-code, and confirm that supported values match. Missing inspection data and an unresolved exact profile also block. The setting is synchronized into Klipper automatically.

Regular and initial-layer build-plate temperatures are inspected independently. Moonraker's `first_layer_bed_temp`, the managed `BED_TEMP` start value, and the first bed-heating command are initial-layer evidence only. Filament Manager compares the regular build-plate temperature only from the managed start boundary's resolved `REGULAR_BED_TEMP`; it never substitutes an initial-layer value or Cura's saved `SETTING_3 material_bed_temperature` quality-layer value for missing resolved material evidence.

`Blocked` in Print History means the inspection found a condition that the blocking policy would reject. The printer pauses only when Cura entered the required `FILAMENT_MANAGER_START_PRINT ... MATERIAL_GUID=<managed-guid>` macro gate after resolving Cura's `{material_guid, 0}` token. A print started through another machine start sequence can still be inspected and recorded, but Filament Manager cannot retroactively pause it; Print History identifies this case explicitly.

## Print sequence

1. Select a managed product material in Cura and send the print. Do not slice with a `Template <material type>` entry.
2. The Filament Manager workstation agent saves `FILAMENT_MANAGER_START_PRINT MATERIAL_GUID={material_guid, 0} BED_TEMP={material_bed_temperature_layer_0, 0} REGULAR_BED_TEMP={material_bed_temperature, 0} EXTRUDER_TEMP={material_print_temperature_layer_0, 0} CHAMBER_TEMP={build_volume_temperature}` as the matched Cura printer's start G-code.
3. In blocking mode, Fluidd shows the inspection prompt while Filament Manager reads the documented Moonraker file metadata and G-code download endpoints. In warning mode, inspection remains auditable without pausing this step.
4. If the currently loaded physical spool is an eligible exact match, the macro calls the existing `START_PRINT` with its original temperature values. No unload/load motion runs.
5. If the spool does not match, Fluidd asks for one exact eligible Spoolman spool. The existing unload routine runs at the loaded filament profile temperature. Only after motion completes does Spoolman become empty.
6. The nozzle preheats to the selected replacement's profile temperature. Insert that exact spool and choose **Filament Inserted - Load**. The existing load routine runs, then the new ID becomes active in Spoolman.
7. Remove purge waste and choose **Start Print**. The unchanged printer `START_PRINT` continues.

Filament Manager delays the print's starting spool snapshot until the preflight/load prompt is complete. Aborting before unload keeps the old active spool. Aborting after unload keeps Spoolman empty. Aborting after load keeps the newly loaded spool active. No future target is recorded as loaded early.

## Manual load and Spoolman selection

Run `LOAD_FILAMENT` or `FILAMENT_MANAGER_LOAD_TARGET` with no parameters in Fluidd to open the current manual-load list. It contains each projected, non-empty spool that has a safe nozzle temperature from its newest non-archived exact printer/nozzle profile or linked in-scope template. Manual loading does not require a current exact print profile, while Cura preflight does. There is no Target Spool field to configure. During a print, M600 unloads the tracked filament, clears Spoolman after motion completes, and opens the same replacement chooser. Running M600 or `FILAMENT_MANAGER_LOAD_TARGET` again while that selection is pending reopens the chooser.

A non-null spool selected directly in Spoolman is treated as the requested target, not proof of a physical load. Within the next 5-second state pass, Fluidd opens the guarded confirmation and the worker restores Spoolman's active ID to the last completed physical boundary. If no spool is tracked, choose either **It Is Already Physically Loaded** to adopt the selected spool explicitly or **Insert and Load It** to run the load routine. If another spool is tracked, confirm the unload/load workflow. Filament Manager changes its active-spool record only after that confirmation or completed load. A direct Spoolman clear never claims that a physical unload occurred.

If a prompt was closed, run `FILAMENT_MANAGER_LOAD_TARGET` to reopen a pending selection. Run `FILAMENT_MANAGER_SPOOL_STATE` to see the current phase, and use `FILAMENT_MANAGER_ABORT` only when the pending workflow should be cancelled. The last completed physical boundary remains authoritative after cancellation.

Run `SELECT_BUILD_PLATE` without parameters to open a chooser generated live from Klipper's saved meshes. Only exact `P<number>` Side A and `P<number>b` Side B names are shown; selecting one loads that same-named mesh and persists the plate side.

## Print history and assessment

The worker checks current print state every five seconds and incrementally imports the supported Moonraker history. New records retain the exact printer, physical spool, material/profile snapshot, plate side, nozzle, G-code SHA-256, supported Cura/Moonraker metadata, predicted/actual use, timestamps, canonical result, and exact bounded Moonraker history outcome such as cancellation, Klippy shutdown, disconnection, or interruption. An `M600` closes the current immutable material segment and opens a new exact segment after the replacement is loaded. Print History loads newest-first in server-side pages of 10 by default, with 25, 50, and 100 choices and complete page navigation.

History from before 0.2.1 is imported but marked legacy/unresolved when its exact canonical material state cannot be reconstructed. The app does not guess missing spool or profile history.

After a print ends, an Operator or Administrator can directly save an Excellent, Successful, Acceptable, or Failed assessment with supported defect tags and notes. Updating the outcome retains the earlier assessment in immutable history. Profile comparisons calculate success statistics from the latest assessment for each print and clearly mark low sample sizes.

## Macro reference

[`integrations/klipper/filament-manager-macros.cfg`](../integrations/klipper/filament-manager-macros.cfg) is the complete required application macro reference. It must be included last. Filament Manager owns public `M600`, `LOAD_FILAMENT`, and `UNLOAD_FILAMENT` without `rename_existing`; no other included file may define those commands. Keep the printer's physical movement bodies under the exact reserved `_FILAMENT_MANAGER_HARDWARE_LOAD` and `_FILAMENT_MANAGER_HARDWARE_UNLOAD` macro names. The reference continues to wrap the existing public `CANCEL_PRINT` and calls—but does not define or replace—the existing `START_PRINT` and `END_PRINT` macros.

The workstation agent overwrites the matched Cura printer's saved start script with the start call above and its saved end script with `END_PRINT` whenever it installs or repairs a managed library. No manual Cura script setup is required. Keep Cura closed while the agent applies the update; any later script drift is backed up and replaced on the next synchronization.

The application additionally uses:

- `FILAMENT_MANAGER_GCODE_INSPECTION` for the worker's blocking inspection result;
- `FILAMENT_MANAGER_SPOOLMAN_TARGET` for worker-mediated confirmation of a direct Spoolman selection;
- `FILAMENT_MANAGER_UNLOAD_SPOOL` for the in-app physical unload/clear request; and
- `FILAMENT_MANAGER_CLEAR_BUILD_PLATE` for the in-app active plate-side and mesh clear request.

Do not invoke underscore-prefixed helpers manually. Keep Moonraker, Fluidd, Klipper, Spoolman, and the printer network within the trusted operational boundary.
