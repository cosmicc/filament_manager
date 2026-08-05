# 10 - Cura Material Profiles and Settings

## Scope

Filament Manager stores calibrated material profiles and exports data that can be transformed into Cura material and quality/profile definitions.

## Profile scope

A profile is not global to a filament name. It is scoped by:

- filament product
- printer
- nozzle diameter
- optional layer-height range
- version

## Required settings

| Group | Field |
|---|---|
| Temperature | Chamber temperature |
| Temperature | Extruder temperature |
| Temperature | Bed temperature |
| Extrusion | Flow percentage |
| Speed | Default print speed |
| Speed | Outer wall speed |
| Speed | Inner wall speed |
| Speed | Infill speed |
| Speed | Top/bottom speed |
| Speed | Initial layer speed |
| Speed | Travel speed |
| Speed | Support speed |
| Speed | Bridge speed |
| Retraction | Retraction distance |
| Retraction | Retraction speed |
| Cooling | Cooling enabled |
| Cooling | Minimum fan percentage |
| Cooling | Maximum fan percentage |
| Support | Support overhang angle |
| Tree support | Maximum branch angle |
| Klipper | Pressure advance factor |
| Material | Filament density |
| Build surface | Preferred build plate |
| Ironing | Optional enabled/flow/speed/spacing |

## Future fields

Store additional Cura settings in a namespaced JSON object with schema version, but promote frequently used stable fields to typed columns through migrations.

## Profile lifecycle

- draft
- calibration in progress
- validated
- published
- superseded
- archived

Published versions are immutable. Editing creates a new draft derived from the prior version.

## Export behavior

Provide:

- human-readable JSON
- Cura-oriented material profile output
- API endpoint for profile retrieval
- checksum and profile version in exported metadata

Cura import compatibility varies by Cura version and printer definition. Keep export templates versioned and test them against the selected Cura release.

## Klipper application

Pressure advance may be applied at print start through an explicit macro or slicer start G-code generated from the selected profile. Filament Manager must not silently change printer configuration files.

## Validation

- cooling minimum <= maximum
- all fan values 0-100
- positive density
- temperatures inside configured hardware limits
- pressure advance inside configured safety limits
- preferred plate exists and is active

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
