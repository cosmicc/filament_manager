# Printer connections and dashboard

A spool must be physically unloaded from its current printer before loading it on another. Load catalogs exclude other printers' loaded spools, and synchronization refuses to transfer their ownership silently.

In **3D Printers**, use **Add 3D printer** for a new Moonraker instance or **Connection** to adopt an existing deployment-defined printer. Saving an existing connection preserves its canonical identity and history; future deployment-variable edits no longer overwrite that connection. Disabled app-owned connections suppress the corresponding deployment fallback.

Use an explicit HTTP/HTTPS origin on a trusted printer network, without a path or embedded credentials. HTTPS verifies certificates normally. The API key is write-only, encrypted in PostgreSQL, and never returned in printer listings, dashboard data, Google publication, or audit events. The connection editor shows only whether a key exists. Blank keeps an existing key; removing it requires an explicit checkbox. See [credential/key recovery](GOOGLE_SHEETS.md#guided-setup-080).

Endpoint changes and disabling an established connection require live idle confirmation and no pending physical commands. If Moonraker is unreachable, physical configuration remains locked. Restore connectivity before changing that connection. A newly entered, never-contacted app connection with no spool, plate, print history or pending physical commands can be corrected without a live check. Load and unload requests identify one printer explicitly; with multiple connections, the server refuses ambiguous legacy requests instead of choosing the first printer.

The Dashboard's previous/next buttons and **All printers** overview choose one printer context. Status, active spools, active plate, and load/plate shortcuts change together. Inventory metrics remain workshop-wide and appear at the bottom. **Sync to Cura** queues full canonical settings only for managed workstations reporting a matching printer code/name; Cura still must close before files are replaced. Match the Cura machine's name to the app printer name if no workstation is found.

Printer hardware settings include heated chamber, maximum extruder/bed temperatures, and independent hotend count. These are recorded capabilities, not commands that change Klipper's configured safety limits.

## Independent hotends

Each printer can retain one physical spool per configured hotend. T0 maps to `extruder`, T1 to `extruder1`, and so on (up to 16). Choose the printer and hotend in the spool's load controls. Unloading targets the spool's exact slot and leaves the other hotends loaded. The Dashboard and 3D Printers show every loaded slot; telemetry uses the currently selected hotend's temperature.

Before enabling **Multi-hotend routines verified** in printer settings:

- Install the current Filament Manager macro reference while idle.
- Retain working printer-owned `T0`, `T1`, etc. macros. Filament Manager does not supply parking, docking, homing, or offset logic.
- Add `FILAMENT_MANAGER_TOOL_CHANGED` as the final command after each T-number macro completes its physical selection. This updates Moonraker/Spoolman's single currently extruding spool without clearing the other loaded slots. The app's explicit load/unload wrappers also verify that the requested extruder became active.
- Verify `_FILAMENT_MANAGER_HARDWARE_LOAD`, `_FILAMENT_MANAGER_HARDWARE_UNLOAD`, and `PURGE_FILAMENT` operate on the selected hotend. The supplied single-hotend operator configuration must not be assumed suitable for a multi-hotend printer: references such as `printer.extruder` must be reviewed against `printer[printer.toolhead.extruder]`, including heater commands and movement.
- Verify the existing printer/nozzle material profile supplies suitable loading temperatures for each tool. This release does not create per-tool nozzle inventory or change Cura's position-zero profile/nozzle ownership.

App-requested multi-hotend motion is disabled until that confirmation is saved, and queued requests recheck it. Never enable it solely because the hotend count is correct. Confirm each physical load through Fluidd, and test each tool while idle before printing. Do not change tools while an insertion/load prompt is pending.

Managed Cura print starts still identify the position-zero material. Select T0 using the printer's safe macro before starting a file; preflight refuses a different active hotend rather than loading the T0 material into it. Spool workflows reject a target already loaded on another hotend before unloading, and insertion/purge confirmations reject a changed active tool.

The completed-tool hook keeps Spoolman's usage attribution aligned with the selected spool. Klipper's aggregate print counter cannot prove exact per-spool usage across tool changes between ten-second captures, so multi-hotend history retains that quantity/cost as incomplete instead of charging the entire print to one sampled spool. Existing single-hotend/M600 accounting is unchanged.

## Filament availability at print start

The managed start boundary holds the file before printer startup while the worker checks the loaded spool. It compares the slicer's estimated grams with remaining filament, without a safety margin; when only estimated length is available it converts that length using filament diameter and density. Insufficient or unavailable values open a Fluidd dialog with **Cancel Print** and **Override and Continue**. This check also runs under the G-code inspection **Warn and continue** policy. Overrides apply only to that start and are retained with the inspection evidence.

This is an estimate, not a guarantee against runout. It checks the selected spool; a multi-material file's aggregate estimate is not per-tool consumption evidence. Keep the existing runout/M600 handling available. Files that bypass `FILAMENT_MANAGER_START_PRINT` also bypass its start gates; no running file is rewritten.

## Powered off versus printer error

Set **Moonraker power device** to the exact switch name from `moonraker.conf`; the default `printer` matches the supplied power-off macro. Blank disables detection. When Klipper is not ready, the app reads that device through Moonraker's supported [power-state endpoint](https://moonraker.readthedocs.io/en/latest/external_api/devices/#get-device-state). Confirmed `off` displays **Powered off**; on/unknown/controller-error states retain the Klipper or connection status. No extra power request runs during healthy printing, and the app does not turn power on or off.

## Completed-print acknowledgement and idle timers

The complete printer-specific file and step-by-step pause/idle installation instructions are in [Pause parking and idle shutoff](PAUSE_PARK_SETUP.md).

Install the updated app macro reference only while idle, then run `FIRMWARE_RESTART`. In the printer-owned `END_PRINT`, call `FILAMENT_MANAGER_PRINT_COMPLETE` before showing the completion prompt and use `FILAMENT_MANAGER_PRINT_ACKNOWLEDGE` for its OK button. Acknowledgement makes Dashboard show Idle for that exact completed duration without resetting `print_stats` or modifying immutable print history.

The Dashboard reads standard Klipper idle-controller state and timeout, plus optional `_POWER_OFF_TIMER_STATE.active` and `.deadline` fields. The deadline uses `toolhead.estimated_print_time` from the same status query. A countdown is shown only while idle and valid, never as proof of electrical power state. Missing macros or an unavailable connection remain explicitly unknown.

For the supplied custom macro file, the separately prepared operator copy uses a 30-minute automatic countdown after the existing 10-minute idle timeout and a 60-minute manual reset. A new print cancels the old countdown. It retains the original motion routines and requires operator review/installation; no live configuration is changed automatically. Reconcile any duplicate `BED_MESH_CALIBRATE` wrappers while preserving probe safety checks before installing a combined configuration.
