# Build plates and automatic heightmaps

The 0.7.6 interlock update blocks ordinary plate, nozzle, and spool changes while printing or paused. Use explicit M600 for an intentional filament replacement. Its native mesh-load and spool execution guards require updating the included macro file and restarting firmware while idle; app preflight restoration remains supported.

Version 0.7.4 keeps the app-selected build plate and its exact saved Klipper mesh aligned. Side A uses `P<number>`; Side B uses `P<number>b`. Select the side that is physically installed—software cannot detect a physical plate swap.

## Upgrade the printer integration

Back up the canonical database and current printer configuration. While the printer is idle, replace the file named by its active include with [the complete macro reference](../integrations/klipper/filament-manager-macros.cfg). Keep `[bed_mesh]`, `[save_variables]`, and the existing integration prerequisites. The reference now wraps native `BED_MESH_CALIBRATE` and `BED_MESH_PROFILE`; remove or reconcile any other wrappers of those two commands before including it. Preserve the native bed-mesh module and the existing hardware load/unload routines. Run `FIRMWARE_RESTART` only when no print is active and verify that `FILAMENT_MANAGER_SPOOL_STATE` reports `0.7.6`.

Your startup block can remain unchanged:

```ini
[delayed_gcode PRINTER_STARTUP]
initial_duration: 3
gcode:
  LIGHTON
  CHECK_PROBE_REMOVED
  G28
  SELECT_BUILD_PLATE
```

The final command now loads the persisted selected side without prompting. Light, probe-safety, and homing behavior remain printer-owned. Select the installed side in the app once after upgrading, allow synchronization, and verify the exact loaded mesh before testing a restart. The app's canonical choice wins during normal idle reconciliation; explicit new selections through the printer macro are imported. Restoring a mesh does not count as another activation.

If the app is offline, Klipper uses its locally persisted selection. When connected, the app repairs stale loaded state while idle. An empty or missing mesh does not erase the app selection or select another side. Startup reports the missing mesh; managed print preflight refuses to proceed until the selected side has an available mesh. No synchronization switches a mesh during printing, pause, or probing.

Open the optional Fluidd chooser with `SELECT_BUILD_PLATE CHOOSE=1`, or choose an exact side with `SELECT_BUILD_PLATE PLATE=P4b`. A successful native `BED_MESH_PROFILE LOAD=P4b` while idle also records that exact side as a manual selection. Non-P-number profiles never become plate identities, and loads never count as calibration. App-driven and startup restoration do not produce manual-selection receipts.

## Selection troubleshooting

If selecting a plate reports `printer_busy` despite an idle printer, 0.7.4 confirms live print/probe state instead of trusting a retained in-progress history row. Unknown or unreachable state still blocks selection safely. The worker checks stale rows before resuming idle synchronization, without rewriting print history.

The message **selected plate mesh unavailable** means the persisted side is unset or its exact saved mesh is missing. After upgrading the app and included macros, choose the physically installed side in the app, or use `SELECT_BUILD_PLATE CHOOSE=1` while idle. Confirm that the matching saved `P<number>`/`P<number>b` mesh exists; save a newly calibrated mesh with the normal `SAVE_CONFIG` workflow. Do not bypass the missing-mesh print gate.

## Calibration and activity dates

Run the normal `BED_MESH_CALIBRATE` after selecting the installed side, or explicitly supply `PROFILE=P4b`. Successful full-bed calibration records that exact side. Default-profile calibration also saves the completed mesh under the selected side's P-number. Use the normal `SAVE_CONFIG` workflow to retain the actual mesh across restarts; the separately persisted receipt is evidence, not a replacement for saving the mesh configuration. Adaptive/custom non-P-number meshes, failures, cancellations, and loading/saving an old profile do not count as full-side calibration.

The worker establishes a clock anchor once per connected Klipper boot using its existing idle status query. Calibrations before that anchor are retained with an unknown exact time; the page separately shows when the app detected them. Mesh reminder intervals then begin conservatively at detection. No historic calibration date is inferred from mesh availability or a load operation.

Last printed uses the latest attributed print start, including interrupted prints. Last activated uses recorded changes of physical plate/side; repeated polling and startup restoration do not advance it. Older dates remain unknown when no reliable evidence exists.

Cleaning tracking, its historical records, and notifications are removed by the database upgrade. Stop the old web and worker processes before the first 0.7.3 migration, then upgrade both together; the removed columns are not compatible with running 0.7.2 processes. Mesh evidence and immutable print history remain. A schema downgrade cannot restore deleted cleaning history; use the pre-upgrade backup if it is needed.

Before deployment testing, verify startup restore with the app online and offline, a missing mesh, a successful calibration, an aborted calibration, and unchanged dates after ordinary mesh loads. Local automated tests do not substitute for this idle-printer check.
