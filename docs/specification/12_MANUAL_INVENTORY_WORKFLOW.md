# 12 - Manual Inventory and Label Workflow

## First-release workflow

The initial release uses labels and manual measurements. Scale and NFC hardware are deferred.

## New spool

1. Select or create the filament product.
2. Assign the next human spool code.
3. Enter nominal filament weight, tare, purchase data, and cost.
4. Print a label with spool code, QR code, material, color, and optional vendor.
5. Enter initial gross weight if measured.
6. Project the spool to Spoolman.
7. Publish the record to Google Sheets.

## Loading a spool

1. Scan or type the label code.
2. Confirm spool identity and remaining mass.
3. Request **Load spool** in Filament Manager or select it in a guarded Fluidd prompt.
4. Let the existing unload routine finish; Spoolman then records no active spool.
5. Insert only the exact prompted spool and confirm insertion in Fluidd.
6. Let the existing load routine finish; only then does Spoolman record that spool as active.
7. Confirm build plate and mesh, then continue the Cura print.

## Manual weighing

1. Stop feeding and place the spool in a repeatable stable position.
2. Find the spool by scan or code.
3. Enter gross weight.
4. Review tare and calculated remaining mass.
5. Confirm large variances.
6. Save the immutable measurement.

## Label contents

- large human spool ID
- QR code containing a stable application URL or spool UUID
- material and color
- vendor/product
- tare mass when useful
- do not encode credentials or mutable remaining mass

## Lost/damaged label

Search by vendor, product, color, and purchase information. Reprint the same spool ID; do not create a duplicate spool.

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
