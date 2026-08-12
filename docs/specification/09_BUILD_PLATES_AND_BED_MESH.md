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
- last cleaned
- per-side last mesh calibration
- per-side latest Moonraker mesh availability and check time
- clean/maintenance notes
- photos later

All current non-photo fields are editable in Filament Manager. The mesh-derived side identity, physical P-number identity, and exact same-named Klipper mapping remain immutable.

## Mesh integration

Map each `build_plate_surface.klipper_mesh_profile` to its identical surface code. Selection executes:

```gcode
BED_MESH_PROFILE LOAD=P1
```

Side B uses its suffixed name:

```gcode
BED_MESH_PROFILE LOAD=P4b
```

The provided macro validates exact `P<number>` or `P<number>b` input, stores the active side, and loads the matching same-named mesh. Invalid names fail before any caller-controlled value can become a G-code command.

## Moonraker synchronization

The Administrator Build Plates action queries Moonraker's `bed_mesh` printer object. Every saved profile whose name exactly matches `P<number>` or `P<number>b` is created immediately if absent. Synchronization groups both sides under one physical P-number plate and preserves existing physical and side metadata. Records are never deleted when a mesh is missing; availability and latest check time are updated on the side independently from physical plate status.

When `bed_mesh.profile_name` is a discovered plate-side mesh, the selected printer's canonical active physical plate and active side are updated together. An empty, unsaved, or invalid profile does not overwrite the recorded selection.

## Existing prompt script

Do not replace the user's existing prompt workflow. Add a stable integration point:

- script passes selected side code to `SELECT_BUILD_PLATE PLATE=P1` or `SELECT_BUILD_PLATE PLATE=P4b`, or
- macro updates a saved variable that Filament Manager reads from Moonraker.

## Preferred build plate

A material profile may specify a preferred plate side. This creates a warning or default suggestion, not an automatic physical assumption.

## Print-start guard

Configurable behaviors:

- off
- warn when no active plate is recorded
- require plate selection
- warn when selected plate differs from the material profile preference
- optionally require the corresponding mesh to be loaded

## Maintenance

Track whole-plate cleaning separately from side-specific mesh calibration and availability. A physical plate can remain usable while one side's mesh is stale or temporarily missing. Define configurable reminders by days or print-hours.

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
