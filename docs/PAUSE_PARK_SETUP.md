# Pause parking and idle shutoff — FLSun QQ-S

The complete [QQ-S macro file](../integrations/klipper/examples/flsun-qq-s-macros.cfg) preserves the supplied hardware routines and adds the 0.8.0 pause and idle-timer changes. It is printer-specific, not a general multi-tool configuration.

## Install while idle

1. Back up your current `macros.cfg`, the included app macro file, and saved variables. Do not replace configuration during a print or pause.
2. Replace `macros.cfg` with the complete QQ-S file. Retain your existing hardware/pin configuration in `printer.cfg`.
3. Save the matching [app macro reference](../integrations/klipper/filament-manager-macros.cfg) beside it as **`filament-manager_macros.cfg`**, matching the include at the bottom. Include the QQ-S file only once. Do not separately include the app file a second time.
4. Remove conflicting PAUSE/RESUME/M24/M25/M0/M1/G28 definitions from other macro includes if present, retaining any additional printer-specific safety requirements. The QQ-S file uses optional before/after hooks for its removable probe; only the app reference defines `BED_MESH_CALIBRATE`.
5. Run `FIRMWARE_RESTART` while idle. Verify `FILAMENT_MANAGER_SPOOL_STATE` reports 0.8.0. Confirm the existing saved `park_x`/`park_y`; without them the supplied default remains maximum X, Y=0.
6. With the bed clear, test homing, safe parking and cancellation. Then supervise a small test print: user pause, repeated pause, resume, M25/M24, and your actual runout sensor. Verify that your sensor uses `pause_on_runout: true` or calls `PAUSE`/`FILAMENT_RUNOUT`/`M600`; do not call renamed native pause commands directly.

## Pause and resume behavior

- User/Fluidd pauses, runout, M600, and slicer M0/M1/M25 stops use the same saved position. A repeated pause cannot replace it with the park position.
- The first pause stops the stream, captures position and G-code modes, explicitly selects relative extrusion for a bounded retract if warm, lifts up to 10 mm within the delta's safe lower region, and moves to the existing park XY. It never calls the fixed-height `PARK_NOZZLE` during a print.
- Resume restores the saved coordinate frame, primes only the recorded retract, returns at the saved clearance height above the original XY, then lets Klipper restore the original Z and G-code state before releasing the stream. M24 follows the same path when physically paused.
- Near the delta's upper cone, with invalid park coordinates, without homing, or during preflight, the printer remains paused without XYZ parking. It does not lower into the model to reach the park station. Pre-print inspection/filament/mesh M25 holds remain nonmoving.
- Resume refuses a lost/unhomed position, changed hotend, cold extruder, unfinished app workflow, or unsafe manually changed return height. Reheat manually when needed. Complete the app's load/confirmation prompt before using Resume. Homing is blocked while paused; cancel before homing. Cancellation invalidates the saved return state.

Do not manually move a parked print into the model, alter offsets/mesh, disable motors, or call native aliases while paused. Emergency shutdown, power loss, firmware restart, skipped steps, and third-party macros that bypass PAUSE cannot provide a trustworthy automatic return. No motion is attempted after a firmware fault. Software/template tests are not a physical clearance certification; the first printer test must be supervised.

## Idle shutoff and completed-print acknowledgement

The existing idle timeout remains 10 minutes. It then starts a 30-minute automatic shutoff countdown; manual reset starts 60 minutes. `_POWER_OFF_TIMER_STATE` exposes its active flag and deadline to the app without added polling. Starting a print cancels the old countdown. Active/paused jobs retain their motors and are not treated as idle shutdown candidates.

The completed-print OK button calls `FILAMENT_MANAGER_PRINT_ACKNOWLEDGE`, making the app display Idle for that completed job without changing print history. See [printer setup](PRINTER_CONNECTIONS.md) for multi-printer, power-device and multi-hotend requirements.
