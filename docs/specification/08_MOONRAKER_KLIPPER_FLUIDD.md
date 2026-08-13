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

## Physical spool authority and macros

The complete required reference is `integrations/klipper/filament-manager-macros.cfg`. Include it after the printer's existing motion macros. It uses `rename_existing` wrappers so the printer's current `LOAD_FILAMENT`, `UNLOAD_FILAMENT`, `M600`, and `CANCEL_PRINT` behavior remains the physical implementation. It never replaces `START_PRINT` or `END_PRINT`.

`FILAMENT_MANAGER_SPOOL_STATE` persists the last completed physical boundary:

- the old ID stays active while the existing unload routine is running;
- after that routine and its `M400` finish, the macro clears active Spoolman state and persists no loaded spool;
- the target ID remains inactive while preheating, waiting for insertion, and running the existing load routine; and
- after that load routine and its `M400` finish, the macro persists and activates the exact target ID.

Public `LOAD_FILAMENT`, `SET_ACTIVE_SPOOL`, and Inventory **Load spool** actions therefore request the same confirmed physical workflow instead of changing metadata directly. Public `UNLOAD_FILAMENT` and `CLEAR_ACTIVE_SPOOL` run physical unload before clearing. `M600` retains pause, unload, purge-more, temperature restore, and resume behavior but requires an exact Fluidd Target Spool through `FILAMENT_MANAGER_LOAD_TARGET` before loading.

The same file provides the existing bounded plate behavior: `SELECT_BUILD_PLATE` accepts only exact `P<number>` Side A or `P<number>b` Side B values before passing the value to `BED_MESH_PROFILE LOAD`.

## Cura print preflight

Cura calls `FILAMENT_MANAGER_START_PRINT` with `{material_guid}` and the existing bed, nozzle, and chamber temperature placeholders. The worker publishes a bounded mapping from each current managed product-material GUID to eligible projected Spoolman IDs, safe Fluidd labels, and the published profile nozzle temperature.

If the persisted loaded ID is one of the candidates, the wrapper immediately hands the original values to the unchanged `START_PRINT`. Otherwise it pauses virtual-SD execution, prompts in Fluidd for the exact matching spool, unloads the old spool at its stored profile temperature, clears Spoolman, preheats to the new profile temperature, waits for insertion confirmation, calls the existing load routine, activates the selected ID, and then hands off to `START_PRINT`. No candidates is a fail-closed print block. Generic templates do not identify a physical product and are not eligible print materials.

## Fluidd

Fluidd remains the prompt and operational display for:

- selecting the exact requested spool in Filament Manager prompts or the `FILAMENT_MANAGER_LOAD_TARGET` Target Spool control
- view remaining filament
- scan compatible labels where supported
- warn about insufficient remaining filament
- compare spool material with slicer metadata

Disable Fluidd's **Show spool selection dialog on print start** setting because its independent selection path activates a spool before physical loading. The global Spoolman **Change Spool** control must not be used for future targets. Filament Manager repairs that kind of direct active-ID drift to the last completed physical macro boundary on the next 15-second state pass, including while a guarded workflow is pending.

If Fluidd is served from a different browser origin than Spoolman, add the exact origin, including scheme and port when non-default, to `SPOOLMAN_CORS_ORIGIN`.

## Security

Spoolman has no built-in user authentication. Keep the printer-facing endpoint on trusted networks, apply firewall restrictions, and place browser access behind an authenticated reverse proxy when remote access is required.

## Filament Manager relationship

Filament Manager reads and reconciles Spoolman through the API and does not proxy Moonraker's normal usage traffic. Every 15 seconds it reads both Moonraker's supported active Spoolman ID and `FILAMENT_MANAGER_SPOOL_STATE`. After one-time initialization, the persisted macro ID represents the last completed physical boundary in every phase. When the remote active ID differs, the worker repairs Moonraker/Spoolman to that value before aligning canonical state. The worker also refreshes the bounded material/spool/temperature catalog when published profiles or eligible inventory change.

The same automatic state pass reads Build Plates through Moonraker's supported `POST /printer/objects/query` endpoint. Filament Manager reads `bed_mesh.profiles`, groups exact P-number A/B side meshes under physical plates, tracks missing meshes without deletion, and uses `bed_mesh.profile_name` to align the active physical plate and side.

Every 5 minutes by default, Filament Manager reads `/server/info`, `/printer/info`, `configfile.settings`, and the documented `toolhead` envelope to discover Moonraker/Klipper versions, sanitized hostname, kinematics, nozzle diameter, and build volume. Connection URLs, process details, and paths never reach the browser. Manufacturer, model, nozzle material, extruder type, and notes remain editable manual fields.

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
