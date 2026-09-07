# 09 - Build Plates and Bed Meshes

## Current baseline

The printer currently uses build-plate names and Klipper mesh profiles:

- `P1`
- `P2`
- `P3`
- `P4`
- `P5`

These are the immutable initial physical identifiers. An unsuffixed mesh is Side A: `P4` means physical plate P4 with Side A facing up. A lowercase `b` suffix is Side B: `P4b` means the same physical P4 plate with Side B facing up. Additional physical plates continue the exact uppercase sequence (`P6`, `P7`, `P10`, and so on), with optional same-number B sides (`P6b`, `P7b`, `P10b`). Leading zeroes, uppercase `B`, and descriptive or lowercase plate names are invalid.

## Build-plate record

Recommended fields:

- plate code
- display name
- manufacturer and product
- physical description
- diameter/dimensions
- magnetic/flexible flags
- condition and active status
- printable sides, limited to A and B
- per-side surface material and smooth/textured finish
- per-side Klipper mesh profile name
- preferred material classes
- maximum recommended bed temperature
- last activated and last printed for plate and side
- per-side last mesh calibration
- per-side latest Moonraker mesh availability and check time
- notes
- sanitized photos

All current non-photo fields are editable in Filament Manager. An Operator may add the next physical plate; the server serializes the operation with Moonraker discovery, assigns the next P-number, creates `Build Plate P<number>`, and adds one same-named Side A whose mesh starts unavailable. An Operator may also add the one Side B record under an existing physical plate; the server derives its exact lowercase-b code and initially marks its mesh unavailable. The mesh-derived side identity, physical P-number identity, and exact same-named Klipper mapping remain immutable. Every mesh-unavailable side is visually identified with a distinct warning and the exact Klipper heatmap profile name it needs.

## Mesh integration

Map each `build_plate_surface.klipper_mesh_profile` to its identical surface code. Selection executes:

```gcode
BED_MESH_PROFILE LOAD=P1
```

Side B uses its suffixed name:

```gcode
BED_MESH_PROFILE LOAD=P4b
```

The provided macro validates exact `P<number>` or `P<number>b` input, stores the active side, and loads the matching same-named mesh. With no parameters it restores the saved side without prompting. With `CHOOSE=1` it builds a Fluidd button for each valid exact P-number mesh. Invalid names cannot become G-code commands.

## Moonraker synchronization

The worker queries Moonraker's `bed_mesh` printer object every 10 seconds by default while no print is active. Every saved profile whose name exactly matches `P<number>` or `P<number>b` is created automatically if absent. Synchronization groups both sides under one physical P-number plate and preserves existing physical and side metadata. Records are never deleted when a mesh is missing; availability and latest check time are updated on the side independently from physical plate status.

Completed-print totals are derived from immutable print jobs captured with that exact side and count each completed job once.

Initial adoption may use a discovered active mesh. After initialization, the app owns selection; only a new explicit manual macro selection receipt changes it from the printer. Empty or stale loaded state is restored from canonical selection while idle, never during printing or probing. Calibration receipts have monotonically increasing per-side sequences and retain unknown offline timestamps separately from detection time.

## Fluidd prompt

Run `SELECT_BUILD_PLATE CHOOSE=1` to open the live saved-mesh chooser. Parameterless startup calls restore the persisted exact side automatically. Direct selection remains `SELECT_BUILD_PLATE PLATE=P1` or `SELECT_BUILD_PLATE PLATE=P4b`.

## Preferred build plate

A material profile may specify a preferred plate side. This creates a warning or default suggestion, not an automatic physical assumption.

## Print-start guard

Managed Cura preflight requires the selected side's saved mesh and loads that exact profile. Missing meshes never fall back to another side. See [Build plate setup](../BUILD_PLATE_SETUP.md) for the startup contract and upgrade instructions.

## Calibration and activity

Cleaning and its records are removed. Successful native full-bed probing automatically records side-specific mesh evidence; ordinary profile loads, failed/aborted probes, and adaptive/custom meshes do not. Mesh reminders use configurable days or completed-print counts. The page shows last printed/activated per plate and side, and last calibrated per side, without a maintenance ledger or manual timestamp button. Historical dates remain unknown when evidence is absent.

## Authoritative implementation references

- Spoolman repository and supported databases: https://github.com/Donkie/Spoolman
- Spoolman installation and Docker port mapping: https://github.com/Donkie/Spoolman/wiki/Installation
- Spoolman configuration variables: https://github.com/Donkie/Spoolman/blob/master/.env.example
- Spoolman REST API: https://donkie.github.io/Spoolman/
- Moonraker Spoolman configuration: https://moonraker.readthedocs.io/en/stable/configuration/#spoolman
- Moonraker Spoolman integration API: https://moonraker.readthedocs.io/en/latest/external_api/integrations/#spoolman
- Moonraker printer object query API: https://moonraker.readthedocs.io/en/latest/external_api/printer/#query-printer-object-status
- Moonraker bed mesh printer object: https://moonraker.readthedocs.io/en/latest/printer_objects/#bed-mesh
- Fluidd Spoolman support: https://docs.fluidd.xyz/features/spoolman
- Google Sheets API: https://developers.google.com/workspace/sheets/api
- Docker Swarm stack deployment: https://docs.docker.com/engine/swarm/stack-deploy/
- PostgreSQL documentation: https://www.postgresql.org/docs/
