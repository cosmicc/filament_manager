# Printing Workflow

## Recommended policy

Use **Warn and continue** under **Settings → G-code inspection policy** while testing 0.2.6. Filament Manager still records every mismatch in Print History. Change the setting to **Block mismatches** after the Cura material library, printer macros, and first exact-state records have been verified.

Blocking pauses virtual-SD execution in Fluidd until Filament Manager can resolve the managed material profile, safely inspect the G-code, and confirm that supported values match. Missing inspection data and an unresolved exact profile also block. The setting is synchronized into Klipper automatically.

## Print sequence

1. Select a managed product material in Cura and send the print. Do not slice with a `Template <material type>` entry.
2. Cura calls `FILAMENT_MANAGER_START_PRINT` with the managed material GUID and the existing bed, nozzle, and chamber placeholders.
3. In blocking mode, Fluidd shows the inspection prompt while Filament Manager reads the documented Moonraker file metadata and G-code download endpoints. In warning mode, inspection remains auditable without pausing this step.
4. If the currently loaded physical spool is an eligible exact match, the macro calls the existing `START_PRINT` with its original temperature values. No unload/load motion runs.
5. If the spool does not match, Fluidd asks for one exact eligible Spoolman spool. The existing unload routine runs at the loaded filament profile temperature. Only after motion completes does Spoolman become empty.
6. The nozzle preheats to the selected replacement's profile temperature. Insert that exact spool and choose **Filament Inserted - Load**. The existing load routine runs, then the new ID becomes active in Spoolman.
7. Remove purge waste and choose **Start Print**. The unchanged printer `START_PRINT` continues.

Filament Manager delays the print's starting spool snapshot until the preflight/load prompt is complete. Aborting before unload keeps the old active spool. Aborting after unload keeps Spoolman empty. Aborting after load keeps the newly loaded spool active. No future target is recorded as loaded early.

## Manual load and Spoolman selection

Run `LOAD_FILAMENT` or `FILAMENT_MANAGER_LOAD_TARGET` with no parameters in Fluidd to open the current manual-load list. It contains each projected, non-empty spool that has a safe nozzle temperature from its newest non-archived exact printer/nozzle profile or linked in-scope template. Manual loading does not require a current exact print profile, while Cura preflight does. There is no Target Spool field to configure. During a print, M600 unloads the tracked filament, clears Spoolman after motion completes, and opens the same replacement chooser. Running M600 or `FILAMENT_MANAGER_LOAD_TARGET` again while that selection is pending reopens the chooser.

A non-null spool selected directly in Spoolman is treated as the requested target, not proof of a physical load. Within the next 15-second state pass, Fluidd opens the guarded confirmation and the worker restores Spoolman's active ID to the last completed physical boundary. If no spool is tracked, choose either **It Is Already Physically Loaded** to adopt the selected spool explicitly or **Insert and Load It** to run the load routine. If another spool is tracked, confirm the unload/load workflow. Filament Manager changes its active-spool record only after that confirmation or completed load. A direct Spoolman clear never claims that a physical unload occurred.

If a prompt was closed, run `FILAMENT_MANAGER_LOAD_TARGET` to reopen a pending selection. Run `FILAMENT_MANAGER_SPOOL_STATE` to see the current phase, and use `FILAMENT_MANAGER_ABORT` only when the pending workflow should be cancelled. The last completed physical boundary remains authoritative after cancellation.

Run `SELECT_BUILD_PLATE` without parameters to open a chooser generated live from Klipper's saved meshes. Only exact `P<number>` Side A and `P<number>b` Side B names are shown; selecting one loads that same-named mesh and persists the plate side.

## Print history and assessment

The worker checks current print state every five seconds and incrementally imports the supported Moonraker history. New records retain the exact printer, physical spool, material/profile snapshot, plate side, nozzle, G-code SHA-256, supported Cura/Moonraker metadata, predicted/actual use, timestamps, and result. An `M600` closes the current immutable material segment and opens a new exact segment after the replacement is loaded.

History from before 0.2.1 is imported but marked legacy/unresolved when its exact canonical material state cannot be reconstructed. The app does not guess missing spool or profile history.

After a print ends, an Operator or Administrator can directly save an Excellent, Successful, Acceptable, or Failed assessment with supported defect tags and notes. Updating the outcome retains the earlier assessment in immutable history. Profile comparisons calculate success statistics from the latest assessment for each print and clearly mark low sample sizes.

## Macro reference

[`integrations/klipper/filament-manager-macros.cfg`](../integrations/klipper/filament-manager-macros.cfg) is the complete required application macro reference. It must be included last. It wraps the printer's existing load, unload, M600, and cancel routines and calls—but does not define or replace—the existing `START_PRINT` and `END_PRINT` macros.

The application additionally uses:

- `FILAMENT_MANAGER_GCODE_INSPECTION` for the worker's blocking inspection result;
- `FILAMENT_MANAGER_SPOOLMAN_TARGET` for worker-mediated confirmation of a direct Spoolman selection;
- `FILAMENT_MANAGER_UNLOAD_SPOOL` for the in-app physical unload/clear request; and
- `FILAMENT_MANAGER_CLEAR_BUILD_PLATE` for the in-app active plate-side and mesh clear request.

Do not invoke underscore-prefixed helpers manually. Keep Moonraker, Fluidd, Klipper, Spoolman, and the printer network within the trusted operational boundary.
