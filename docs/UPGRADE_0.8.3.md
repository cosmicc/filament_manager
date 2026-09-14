# 0.8.3 testing upgrade

Back up the canonical database and upgrade web and worker together. This version keeps the existing schema and all historical print/settings snapshots.

## Printer and Cura installation

1. While the printer is idle, back up and replace the included `filament-manager-macros.cfg` with the [0.8.3 reference](../integrations/klipper/filament-manager-macros.cfg). Keep your existing hardware and pause/park routines. Run `FIRMWARE_RESTART` and verify `FILAMENT_MANAGER_SPOOL_STATE` reports `0.8.3`.
2. Upgrade each workstation agent. Close Cura, use **Push app settings**, and wait for **Succeeded** before reopening. Renderer revision 27 refreshes saved machine start G-code automatically.
3. Re-slice prints to include the updated metadata and managed start boundary. Existing uploaded G-code is never rewritten.

Every managed start now waits for inspection. Temperatures above the printer's configured bed/extruder limits, or positive chamber heating on a printer without a heated chamber, block even in warn-only mode. Supported heater maxima are observed throughout the already downloaded file, including later tower sections. Missing inspection cannot certify hardware safety and keeps the gate blocked. Ordinary settings differences remain warnings when that policy is selected. Direct unmanaged starts and arbitrary custom heating macros cannot be certified by this gate.

## Build plate compatibility

Open a saved material template to rate each physical plate side from zero to five stars. Changes save immediately. **Unrated** is allowed but is not a recommendation. Zero means avoid because of possible plate damage and blocks the managed start without a filament-weight override. Five stars is recommended; other positive ratings are suggested in descending order on filament/spool details and the dashboard. Ratings apply to the filament's current exact printer/nozzle template. They are also published to the Google workbook's **Plate Ratings** tab.

The selected plate must be synchronized before starting. Approval is bound to its exact side; changing the side during a deferred start requires cancelling and restarting after synchronization.

The worker creates **Silk PLA**, **PLA Carbon Fiber**, and **PETG Carbon Fiber** templates by copying existing PLA/PETG settings in each matching nozzle scope. Review and calibrate those starting values. Existing filaments, overrides, Silk/Ultra Silk finishes, Carbon Fiber fillers, and print history are preserved. A missing base template is not replaced with guessed settings.

## Cura metadata and timelapse

The agent places this comment block at the top of the machine's start G-code, before `FILAMENT_MANAGER_START_PRINT`:

```gcode
;===== MOONRAKER METADATA =====
;Nozzle diameter = {machine_nozzle_size}
;Filament type = {material_type}
;Filament name = {material_name}
;Filament weight = {filament_weight}
;M109 S{material_print_temperature}
;M190 S{material_bed_temperature}
;M191 S{build_volume_temperature}
;===== END MOONRAKER METADATA =====
```

These are metadata comments, not heater commands. Cura resolves `filament_weight` after slicing and may format it as a per-extruder list.

For layer-triggered timelapse, install/enable Cura's Post Processing plugin, open **Extensions → Post Processing → Modify G-Code**, add **Time Lapse Camera**, and configure it to emit **M240** at every layer. Confirm your printer's timelapse integration handles M240. The app does not install camera hardware or rewrite uploaded files.

## Other changes

- Printer metadata saves tolerate unrelated status updates while retaining real concurrent-edit conflicts.
- Compact dashboard/inventory cards, full-width printer and workstation summaries with detail dialogs, new app icons, and simplified navigation. Print labels remain on each spool's detail dialog.
- Activity pages use 20 events by default, with 50/100/200 choices, whole-history search, and first/previous/next/last controls.
- Print history links captured spool/filament identities, records manufacturer for new prints, separates initial layer height/width, and shows observed variable layer-height ranges. Old missing evidence remains unknown. Dates include at most two elapsed units.
- Missed automatic backups coalesce into one current backup when printing permits. A new schedule occurrence supersedes the older occurrence's retry delay; successful backups restart the interval. Existing retention remains unchanged.
- Confirmed printer power-off shows synchronization checks as waiting. Unknown power or a failed power read still reports the underlying problem.

Automated tests do not certify physical printer motion. After updating macros, verify a safe normal start, an over-limit file, an incompatible plate, and a warn-only calibration print while supervising the printer.
