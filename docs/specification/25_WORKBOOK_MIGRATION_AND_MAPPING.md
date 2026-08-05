# 25 - Workbook Migration and Mapping

## Baseline

The supplied workbook contains 35 populated spool records, 34 inventory columns, and the tabs Dashboard, Inventory, Lists, Wishlist, and Material Reference.

## Migration rule

The workbook is a one-time input. The migration must be dry-run first, produce a row-by-row report, and require explicit approval before committing.

## Existing field preservation

All 34 current inventory fields map to canonical database fields or calculated publication fields. The machine-readable mapping is in `mappings/filament_inventory_columns.csv`.

## New canonical fields

- internal UUID
- record version
- Spoolman IDs
- projection state
- active printer/dryer location
- profile version
- preferred build plate
- label URL
- accepted measurement metadata
- audit metadata

## Calculated fields

The application, not the Google Sheet, calculates:

- inventory status
- remaining filament
- remaining percentage
- used filament
- estimated remaining length
- full spool weight
- cost per gram

## Import validation

- unique/non-empty spool ID
- known material/filler/finish values or explicit new vocabulary
- positive diameter and density
- gross weight not below tare without override
- dates parsed consistently
- cost numeric and non-negative
- suspicious formulas or text escaped

## Google output

The new Google publication retains familiar columns but may add profile, plate, projection, and publication metadata. Users should view it rather than edit it.

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
