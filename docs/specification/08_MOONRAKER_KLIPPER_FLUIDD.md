# 08 - Moonraker, Klipper, and Fluidd Integration

## Moonraker connection

Moonraker connects directly to the Spoolman service through a stable LAN endpoint:

```ini
[spoolman]
server: http://spoolman.internal.example:7912
sync_rate: 5
```

Use a DNS name or virtual IP that remains valid when Swarm reschedules the service. Do not use the overlay-only `spoolman` or `spoolman_spoolman` names on the printer.

## Availability behavior

- Moonraker usage reporting does not depend on the Filament Manager web or worker services being online.
- Restarting or upgrading only the Filament Manager services must not interrupt the Spoolman endpoint.
- Spoolman maintenance is scheduled separately and should preserve queued or recoverable usage reporting according to Moonraker behavior.

## Active spool macros

```ini
[gcode_macro SET_ACTIVE_SPOOL]
gcode:
  {% if params.ID %}
    {% set id = params.ID|int %}
    {action_call_remote_method(
       "spoolman_set_active_spool",
       spool_id=id
    )}
  {% else %}
    {action_respond_info("Parameter 'ID' is required")}
  {% endif %}

[gcode_macro CLEAR_ACTIVE_SPOOL]
gcode:
  {action_call_remote_method(
    "spoolman_set_active_spool",
    spool_id=None
  )}
```

The package also includes `integrations/klipper/filament-manager-macros.cfg`. Its plate macro accepts only exact `P<number>` Side A or `P<number>b` Side B values before passing the same bounded name to `BED_MESH_PROFILE LOAD`.

## Fluidd

Fluidd uses Moonraker's Spoolman integration to:

- select the active spool
- view remaining filament
- scan compatible labels where supported
- warn about insufficient remaining filament
- compare spool material with slicer metadata

If Fluidd is served from a different browser origin than Spoolman, add the exact origin, including scheme and port when non-default, to `SPOOLMAN_CORS_ORIGIN`.

## Security

Spoolman has no built-in user authentication. Keep the printer-facing endpoint on trusted networks, apply firewall restrictions, and place browser access behind an authenticated reverse proxy when remote access is required.

## Filament Manager relationship

Filament Manager reads and reconciles Spoolman through the API. It may also request active-spool changes through Moonraker, but it does not proxy Moonraker's normal usage traffic.

An Administrator may synchronize Build Plates through Moonraker's supported `POST /printer/objects/query` endpoint. Filament Manager reads `bed_mesh.profiles`, groups exact P-number A/B side meshes under physical plates, tracks missing meshes without deletion, and uses `bed_mesh.profile_name` to align the active physical plate and side.

An Administrator may also synchronize useful Printer information. Filament Manager reads `/server/info`, `/printer/info`, `configfile.settings`, and the documented `toolhead` envelope to discover Moonraker/Klipper versions, sanitized hostname, kinematics, nozzle diameter, and build volume. Connection URLs, process details, and paths never reach the browser. Manufacturer, model, nozzle material, extruder type, and notes remain editable manual fields.

## Authoritative implementation references

- Spoolman repository: https://github.com/Donkie/Spoolman
- Spoolman Docker installation: https://github.com/Donkie/Spoolman/wiki/Installation
- Spoolman configuration variables: https://github.com/Donkie/Spoolman/blob/master/.env.example
- Spoolman security guidance: https://github.com/Donkie/Spoolman/wiki/Security
- Spoolman REST API: https://donkie.github.io/Spoolman/
- Moonraker Spoolman configuration: https://moonraker.readthedocs.io/en/stable/configuration/#spoolman
- Fluidd Spoolman support: https://docs.fluidd.xyz/features/spoolman
- Google Sheets API: https://developers.google.com/workspace/sheets/api
- Docker Swarm stack deployment: https://docs.docker.com/engine/swarm/stack-deploy/
- PostgreSQL documentation: https://www.postgresql.org/docs/
