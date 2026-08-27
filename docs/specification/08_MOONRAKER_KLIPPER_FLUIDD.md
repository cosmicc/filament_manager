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

The complete required reference is `integrations/klipper/filament-manager-macros.cfg`. Include it after the printer's existing motion macros. Filament Manager owns public `M600`, `LOAD_FILAMENT`, and `UNLOAD_FILAMENT` without requiring existing public commands or `rename_existing`; another definition of any of those commands is a configuration conflict and must be removed. The printer's unchanged physical routines must be defined first under the exact reserved `_FILAMENT_MANAGER_HARDWARE_LOAD` and `_FILAMENT_MANAGER_HARDWARE_UNLOAD` names. The app file calls those internal routines directly and uses `rename_existing` only to wrap the existing public `CANCEL_PRINT`. It never replaces `START_PRINT` or `END_PRINT`.

`FILAMENT_MANAGER_SPOOL_STATE` persists the last completed physical boundary:

- the old ID stays active while the existing unload routine is running;
- after that routine and its `M400` finish, the macro clears active Spoolman state and persists no loaded spool;
- the target ID remains inactive while preheating, waiting for insertion, and running the existing load routine; and
- after that load routine and its `M400` finish, the macro persists and activates the exact target ID.

Public `LOAD_FILAMENT`, `FILAMENT_MANAGER_LOAD_TARGET`, `SET_ACTIVE_SPOOL`, and Inventory **Load spool** actions therefore request the same confirmed physical workflow instead of changing metadata directly. Calling either manual load macro without an ID opens a live deduplicated list from the bounded manual-load catalog; it does not require a Fluidd-editable macro variable. That catalog includes each projected non-empty spool with a safe nozzle temperature from its newest non-archived exact profile or linked printer/nozzle template, even when no current exact print profile is available. Public `UNLOAD_FILAMENT` and `CLEAR_ACTIVE_SPOOL` run physical unload before clearing. `M600` retains pause, unload, purge-more, temperature restore, and resume behavior and opens the same chooser after unload. Repeating M600 or the target macro during the selection phase reopens that prompt rather than starting another workflow.

The same file provides bounded plate behavior: `SELECT_BUILD_PLATE` accepts only exact `P<number>` Side A or `P<number>b` Side B values before passing the value to `BED_MESH_PROFILE LOAD`. With no parameter, it enumerates `printer.bed_mesh.profiles` live and displays only those valid names as Fluidd buttons.

## Cura print preflight

After Cura initialization, the managed plugin resolves the selected managed material through the global printer stack's supported position-zero extruder and supplies `FILAMENT_MANAGER_START_PRINT MATERIAL_GUID={material_guid, 0} BED_TEMP={material_bed_temperature_layer_0, 0} EXTRUDER_TEMP={material_print_temperature_layer_0, 0} CHAMBER_TEMP={build_volume_temperature}` at slice time, plus `END_PRINT` at the end. The explicit extruder-zero placeholders ensure Cura obtains the material GUID and per-extruder temperatures from the material-bearing extruder stack. The runtime override does not alter stored machine configuration and does not apply to unmanaged materials. The worker publishes a bounded mapping from each current managed product-material GUID to eligible projected Spoolman IDs, safe Fluidd labels, and the current exact profile nozzle temperature.

If the persisted loaded ID is one of the candidates, the wrapper immediately hands the original values to the unchanged `START_PRINT`. Otherwise it pauses virtual-SD execution, prompts in Fluidd for the exact matching spool, unloads the old spool at its stored profile temperature, clears Spoolman, preheats to the new profile temperature, waits for insertion confirmation, calls the existing load routine, activates the selected ID, and then hands off to `START_PRINT`. No candidates is a fail-closed print block. Generic templates do not identify a physical product and are not eligible print materials.

The application setting `gcode_inspection` defaults to `warn`. In `block` mode the same wrapper pauses before spool selection and waits for `FILAMENT_MANAGER_GCODE_INSPECTION`. Missing exact profile state, an unavailable bounded file inspection, or any supported profile mismatch remains blocked. In `warn` mode the evidence is stored without delaying the spool workflow. The worker reads `/server/files/metadata`, streams `/server/files/gcodes/{filename}` once for its SHA-256 plus bounded header/tail samples, and never evaluates Cura content.

Every five seconds by default, the worker reads documented `print_stats`, imports `/server/history/list`, and converges one canonical PrintJob. Exact state capture waits until a pending preflight/load finishes so the previously loaded spool is never treated as the new print's starting spool. M600 creates immutable material segments and refreshes their current actual use. Each exact segment snapshot retains the spool's purchase-cost-per-gram and currency basis so current and historical costs never depend on mutable inventory. Historical jobs with insufficient canonical context are retained as explicitly unresolved instead of guessed.

For current and historical files, the worker reads Moonraker's documented metadata thumbnail list, validates the selected largest relative raster path beneath the G-code root, downloads it under a strict byte limit, decodes it under a pixel limit, strips source metadata by re-encoding it as a bounded WebP, and stores it on the print job. Missing or invalid thumbnails never fail print ingestion. The browser receives only an authenticated Filament Manager thumbnail URL; Moonraker origins, keys, paths, and response bodies remain server-side.

## Fluidd

Fluidd remains the prompt and operational display for:

- selecting the exact requested spool from the live Filament Manager prompt opened by print preflight, M600, `LOAD_FILAMENT`, or `FILAMENT_MANAGER_LOAD_TARGET`
- view remaining filament
- scan compatible labels where supported
- warn about insufficient remaining filament
- compare spool material with slicer metadata

Disable Fluidd's **Show spool selection dialog on print start** setting because its independent print-start selection path activates a spool before physical loading. A non-null direct Spoolman selection made while the physical workflow is idle or waiting for a manual target is captured on the next 15-second state pass and shown as a guarded Fluidd confirmation. The worker immediately restores the operational active ID to the last completed physical boundary. When no spool is tracked, the operator may explicitly confirm that the target is already physically loaded or run the existing load routine; when a different spool is tracked, the unload/load routine is required. A direct clear, invalid target, or drift in another phase is repaired without changing canonical state.

If Fluidd is served from a different browser origin than Spoolman, add the exact origin, including scheme and port when non-default, to `SPOOLMAN_CORS_ORIGIN`.

## Security

Spoolman has no built-in user authentication. Keep the printer-facing endpoint on trusted networks, apply firewall restrictions, and place browser access behind an authenticated reverse proxy when remote access is required.

## Filament Manager relationship

Filament Manager reads and reconciles Spoolman through the API and does not proxy Moonraker's normal usage traffic. Every 15 seconds it reads both Moonraker's supported active Spoolman ID and `FILAMENT_MANAGER_SPOOL_STATE`. After one-time initialization, the persisted macro ID represents the last completed physical boundary in every phase. A valid non-null direct selection may be passed to the guarded target macro only in `idle`, `load_select`, or `manual_select`; Moonraker/Spoolman is then repaired to the physical ID before canonical alignment. All other mismatches are repaired without target capture. The worker refreshes both the strict published-profile Cura catalog and the broader safe manual-load spool/temperature catalog when profiles, templates, or eligible inventory change.

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
