# 13 - Future Dry-Box Scale Adapter

## Goal

Measure the physical spool while filament feeds from the dry box without coupling Filament Manager to a specific load cell, ADC, or microcontroller.

## Practical limitation

A feeding spool experiences vibration, filament tension, friction, and dryer movement. Continuous samples are useful telemetry but are not automatically authoritative. The system accepts a canonical measurement only when stability and operating-state rules pass.

## Event contract

```json
{
  "device_id": "dryer-scale-1",
  "spool_id": "G6",
  "gross_weight_g": 812.4,
  "measured_at": "2026-08-05T00:15:00Z",
  "stable": true,
  "uncertainty_g": 1.5,
  "sequence": 18342,
  "printer_state": "idle"
}
```

## Acceptance policy

- authenticated registered device
- unique device sequence
- known spool identity
- calibrated scale
- plausible range
- stable variance for configured duration
- preferably printer idle or paused with no extrusion movement
- optional operator confirmation for large corrections

## Reconciliation policy

Moonraker usage remains the expected-consumption source between physical measurements. An accepted scale capture corrects expected remaining mass and records variance. The service does not subtract both raw scale drift and Moonraker usage for the same period.

## Calibration data

- zero offset
- calibration factor
- certified/reference mass
- calibration date
- temperature-compensation support
- firmware version
- uncertainty

## Supported transports

- HTTPS ingestion
- MQTT adapter service
- USB serial gateway
- future Moonraker sensor bridge

The core domain consumes normalized events regardless of transport.

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
