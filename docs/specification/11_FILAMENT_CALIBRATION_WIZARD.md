# 11 - New Filament Calibration Wizard

## Objective

Guide the operator through a repeatable sequence that produces a validated, versioned material profile for a specific filament, printer, and nozzle.

## Session setup

Collect:

- physical spool or filament product
- printer
- nozzle diameter
- starting build plate
- target layer height
- current baseline profile
- operator notes

The wizard may be paused and resumed.

## Step 1 - Temperature Tower

Purpose: select the best extruder temperature while recording bed, chamber, cooling, and speed conditions.

Record:

- tested temperature range and increment
- selected extruder temperature
- acceptable range
- visual result notes
- stringing, bridging, surface, and layer-bond observations

## Step 2 - Flow Rate Tower

Purpose: calibrate extrusion multiplier/flow after temperature is selected.

Record:

- test method
- baseline flow
- tested range
- selected flow percentage
- dimensional or wall-thickness observations

## Step 3 - Klipper Pressure Advance Square Tower

Purpose: choose pressure advance for corner quality at the selected temperature and flow.

Record:

- start and factor/increment
- acceleration and speed used
- selected pressure advance factor
- calculation notes

## Step 4 - Retraction Speed and Distance Tower

Purpose: reduce stringing without causing jams, under-extrusion, or excessive wear.

Record:

- distance range
- speed range
- selected retraction distance
- selected retraction speed
- travel/cooling conditions

## Step 5 - Size and Hole Calibration

Purpose: separate product-specific material compensation from possible printer-geometry correction after retraction is stable.

Record:

- recorded design X, Y, and Z dimensions
- actual measured X, Y, and Z dimensions
- recorded design hole diameter
- actual measured hole diameter
- recorded design shaft diameter
- actual measured shaft diameter
- recorded design wall thickness
- actual measured wall thickness
- calculated X and Y expansion observations
- calculated Cura Horizontal Expansion (`xy_offset`)
- calculated Cura Hole Horizontal Expansion (`hole_xy_offset`)
- calculated shaft expansion reference and divergence warning
- calculated material-specific flow from the completed flow baseline and wall measurements
- calculated X/Y/Z material shrinkage percentages
- non-applying X/Y/Z printer scale recommendations

Each horizontal feature correction is `(design - measured) / 2`. Horizontal Expansion is the mean of the X and Y corrections. Hole Horizontal Expansion and shaft reference use their own two-sided differences. Recommended flow is `baseline flow × design wall / measured wall`. Printer scale recommendations are `design / measured × 100`; material shrinkage is `(design - measured) / design × 100`. When X/Y corrections or the shaft reference differ by more than 0.05 mm, classify the result for printer-geometry review. Filament Manager never applies Klipper axis or rotation-distance changes automatically.

## Step 6 - Overhang Test

Purpose: determine practical unsupported angle and support trigger settings.

Record:

- tested angles
- cooling conditions
- acceptable unsupported angle
- selected support overhang angle
- maximum tree-support branch angle
- preferred support notes

## Step 7 - Optional Ironing Test

Purpose: determine whether ironing improves top surfaces for the material.

Record:

- enabled/disabled decision
- ironing flow
- ironing speed
- line spacing
- selected result and notes

## Step dependencies

The wizard enforces the user-specified order because later tests depend on earlier thermal and flow choices. A step can be repeated. Repeating a completed earlier step marks dependent results as needing review.

## Test artifacts

Each step can reference:

- uploaded G-code
- Cura project/profile used
- generated instructions
- optional photograph
- print job ID

The MVP can provide instructions and track user-sliced test files. Automated tower generation can be added later.

## Completion

When mandatory steps are complete:

1. show a consolidated comparison;
2. validate settings against printer limits;
3. select preferred build-plate side;
4. publish a new profile version;
5. queue Spoolman and Google projections;
6. offer Cura export;
7. store pressure advance for the Cura Klipper Settings plugin in the material profile.

## Overrides

An administrator may publish an incomplete profile only with a recorded reason. The profile displays an “incomplete calibration” warning.

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
