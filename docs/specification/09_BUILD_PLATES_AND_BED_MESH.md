# 09 - Build Plates and Bed Meshes

## Current baseline

The printer currently uses build-plate names and Klipper mesh profiles:

- `P1`
- `P2`
- `P3`
- `P4`
- `P5`

These identifiers are immutable unless an administrator performs a controlled rename.

## Build-plate record

Recommended fields:

- plate code
- display name
- manufacturer and product
- surface type and coating
- diameter/dimensions
- magnetic/flexible flags
- condition and active status
- Klipper mesh profile name
- preferred material classes
- maximum recommended bed temperature
- last cleaned
- last mesh calibration
- clean/maintenance notes
- photos later

## Mesh integration

Map `build_plate.klipper_mesh_profile` to the existing Klipper profile name. Selection executes:

```gcode
BED_MESH_PROFILE LOAD=P1
```

The provided macro example validates `P1` through `P5`, stores the active plate, and loads the matching mesh.

## Existing prompt script

Do not replace the user's existing prompt workflow. Add a stable integration point:

- script passes selected plate code to `SELECT_BUILD_PLATE PLATE=P1`, or
- macro updates a saved variable that Filament Manager reads from Moonraker.

## Preferred build plate

A material profile may specify a preferred plate. This creates a warning or default suggestion, not an automatic physical assumption.

## Print-start guard

Configurable behaviors:

- off
- warn when no active plate is recorded
- require plate selection
- warn when selected plate differs from the material profile preference
- optionally require the corresponding mesh to be loaded

## Maintenance

Track cleaning and mesh calibration separately. A plate can remain physically usable while its mesh is stale. Define configurable reminders by days or print-hours.

## Authoritative implementation references

- Spoolman repository and supported databases: https://github.com/Donkie/Spoolman
- Spoolman installation and Docker port mapping: https://github.com/Donkie/Spoolman/wiki/Installation
- Spoolman configuration variables: https://github.com/Donkie/Spoolman/blob/master/.env.example
- Spoolman REST API: https://donkie.github.io/Spoolman/
- Moonraker Spoolman configuration: https://moonraker.readthedocs.io/en/stable/configuration/#spoolman
- Moonraker Spoolman integration API: https://moonraker.readthedocs.io/en/latest/external_api/integrations/#spoolman
- Fluidd Spoolman support: https://docs.fluidd.xyz/features/spoolman
- Google Sheets API: https://developers.google.com/workspace/sheets/api
- Docker Swarm stack deployment: https://docs.docker.com/engine/swarm/stack-deploy/
- PostgreSQL documentation: https://www.postgresql.org/docs/
