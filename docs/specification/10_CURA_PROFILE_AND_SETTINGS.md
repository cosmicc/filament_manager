# 10 - Cura Material Profiles and Settings

## Scope

Filament Manager presents directly saved material templates plus template-linked sparse product overrides. Internally it keeps complete immutable resolved snapshots for audit, exact print history, synchronization, and recovery. A workstation synchronization contains the current library for every matching template and product profile. Cura main/custom profiles remain workstation-owned and unsynchronized. Filament Manager does not create quality-change profiles or patch machine start G-code; it removes only centrally managed material keys from user-created quality changes so those settings cannot supersede the selected material.

Install and enable the Cura **Material Settings** plugin to expose the stored material values and the Cura **Klipper Settings** plugin to consume pressure advance and smooth time.

## Profile scope

A profile is scoped by filament product, printer, nozzle diameter, and optional layer-height range. It directly references the current template snapshot, stores only semantic differences from that base, and retains the resolved snapshot used by Cura. It may reference a preferred build-plate side such as `P4` or `P4b`.

## Approved Cura material catalog

The ordered implementation catalog is `CURA_MATERIAL_SETTINGS` in `src/filament_manager/domain/cura_material_settings.py`. It mirrors the operator's active Cura 5.13 Material Settings configuration and is the central source supplied to every managed workstation deployment. The matching operator checklist is the maintained plain-text file at `docs/CURA_MATERIAL_PRINT_SETTINGS.txt`; an automated test requires every editable key and label to remain identical to the central catalog.

- Temperature: `material_print_temperature`, `default_material_print_temperature`, `material_print_temperature_layer_0`, `material_initial_print_temperature`, `material_final_print_temperature`, `material_standby_temperature`, `material_bed_temperature`, `default_material_bed_temperature`, `material_bed_temperature_layer_0`, `build_volume_temperature`.
- Flow: `material_flow`, `material_flow_layer_0`, `infill_material_flow`, `support_material_flow`, `roofing_material_flow`, `skirt_brim_material_flow`.
- Speed: `speed_print`, `speed_print_layer_0`, `speed_layer_0`, `speed_wall`, `speed_wall_0`, `speed_wall_x`, `speed_infill`, `speed_topbottom`, `speed_roofing`, `speed_support`, `speed_travel`, `speed_travel_layer_0`, `skirt_brim_speed`.
- Retraction: `retraction_enable`, `retraction_amount`, `retraction_retract_speed`, `retraction_prime_speed`, `retraction_min_travel`, `retract_at_layer_change`, `limit_support_retractions`. The legacy `retraction_speed` alias is emitted from Retraction Retract Speed but is not independently editable.
- Cooling: `cool_fan_enabled`, `cool_fan_speed`, `cool_fan_speed_0`, `cool_fan_speed_min`, `cool_fan_speed_max`, `cool_fan_full_layer`, `cool_min_layer_time`, `cool_min_layer_time_fan_speed_max`.
- Geometry and support: `xy_offset`, `xy_offset_layer_0`, `hole_xy_offset`, `hole_xy_offset_max_diameter`, `support_angle`.
- Cura Klipper Settings: `klipper_pressure_advance_factor`, `klipper_smooth_time_enable`, `klipper_smooth_time_factor`.
- Derived read-only material metadata: `material_brand`, `material_type`.

Frequently used settings have typed PostgreSQL columns. Remaining approved settings use versioned `cura_extensions` JSONB. Arbitrary or machine-level Cura keys are rejected.

## Existing-source import

Each paired workstation scans bounded Cura material files with a hardened XML parser and saved `quality_changes` print-profile files with a non-interpolating INI parser. A saved profile's global and position-zero extruder layers are merged, with explicit extruder values winning. Only literal values from the approved tracked catalog are reported; expressions, unsupported keys, machine settings, additional extruders, and absolute paths are omitted. Discovery never modifies the local material or print profile.

Before takeover, Cura Workstations opens an explicit map-then-review dialog that lists every discovered source beside a selector containing the existing active Filament Manager templates plus **Do not import**. Named material and saved print-profile sources remain selectable even when they contain no tracked literal override or all tracked values are safely omitted expressions. An Administrator may map any subset, and each source and template may be used at most once in the batch. The review shows every selected source-to-template mapping and the number of ignored sources; **Back to mappings** returns to the selectors. One **Complete takeover** confirmation applies all mapped literal settings to those templates, cascades normal inheritance to their linked filament profiles, records provenance, enables management, and queues synchronization in one transaction.

Unmapped sources do not create templates or filament profiles and are removed from the managed Cura library only after the workstation backup is complete. The entire takeover is atomic: the server compares the exact reviewed content-hashed source-ID set with the latest reported catalog, so a changed report, unavailable template, duplicate source/template choice, or any failed save leaves management disabled and saves none of the mappings. Routine heartbeats do not invalidate an unchanged review. A clean installation follows the same review and may complete with zero mappings.

After takeover, the workstation agent separately reports approved settings from Filament Manager-prefixed files with known deterministic GUIDs. A semantic change to a known template or product material saves directly and idempotently as the current state, then queues a full-library synchronization. Unknown GUIDs, copied/new Cura materials, metadata edits, and machine settings never create application records; new templates and products can be added only in Filament Manager.

## Template and product lifecycle

Templates are scoped to one printer and nozzle and synchronize to Cura with the exact name `Template <material type>` and brand `Template`. Product materials use their canonical manufacturer as the Cura brand; products without one use the exact `Unknown` brand. The managed plugin adds every matching template root to Cura's favorites. Creating or editing a template saves it immediately and queues a new complete-library checksum for every managed workstation. A new filament product receives a current linked profile containing only differences from its template. Saving a template immediately creates a new current resolved snapshot for every linked filament. Explicitly customized keys remain owned by that filament—even when their value temporarily equals the updated template—while all other keys inherit the new value.

Configured-system seeding creates one recommended `Template ASA` for each configured printer and current nozzle scope only when no ASA template already exists. Its conservative starting values are 245 C nozzle, 95 C bed, 45 C chamber, fan disabled, 50 mm/s print speed, 100 percent flow, and 1.07 g/cm3 density. A reviewed Cura ASA mapping or later direct app edit replaces the applicable current values normally.

Selecting a filament opens its canonical detail, linked template, inherited/customized count, and complete resolved Cura settings editor. Every field starts from the effective linked-template value and explicit customizations are visibly highlighted. Retraction Retract Speed and Retraction Prime Speed are separate controls. Cooling exposes Regular Fan Speed, Maximum Fan Speed, Regular Fan Speed at Layer, Minimum Layer Time, and Minimum Speed; Initial Fan Speed stays hidden and always exports as zero. Overlapping legacy aliases appear only through their one canonical control. Each field identifies its template value; **Reset to Template** removes that explicit customization on save. Saving takes effect immediately, stores only semantic differences, and automatically queues Cura synchronization. Applying calibration results starts from the session baseline and records calibrated differences without duplicating unrelated inherited values.

## Internal snapshot lifecycle

- draft
- calibration in progress
- validated
- published
- superseded
- archived

These status values remain an internal compatibility and history mechanism. Current template/profile snapshots are immutable once created, but the web interface exposes only direct saves and the current state. It never asks an operator to create a revision, publish a draft, or manually deploy Cura settings.

## Synchronization and export

The JSON export downloads as an attachment and includes the semantic profile, complete computed Cura setting map, central managed-key catalog, checksum, version, and deterministic managed material GUID. The workstation agent writes that GUID into Cura XML so `{material_guid}` identifies the exact current product profile during Klipper print preflight. Each generated material description contains `Filament Filler: <value>` and `Filament Finish: <value>` on separate lines, using `None` when the canonical field is empty. The agent matches printer/nozzle entries, waits for Cura to close, backs up the union of existing and desired user material/plugin targets plus every user quality-change file that will be altered or quarantined, atomically applies the exact desired state, removes stale user materials, and retains an idempotent rollback manifest. A local renderer revision is part of that manifest; an upgraded agent rejects an older renderer revision and reports the library stale so the server requeues safe replacement even when the canonical library checksum is unchanged.

The agent parses bounded regular files under the user `quality_changes` directory without interpolation. It removes only central managed material keys, preserves unrelated Cura settings, rewrites recoverable duplicate-section profiles into one valid document, and copies malformed profiles to agent-owned quarantine before removing them from Cura's load path. Symlinks, oversized collections, and oversized files fail safely. Quality cleanup participates in desired-library drift detection, deployment reporting, and rollback. Bundled quality files under Cura's installation are never changed.

Cura resolves user and quality layers before materials. The managed plugin therefore filters selectors to `filament_manager_` roots, favorites Template entries, removes central material keys from the active custom-quality layer, and mirrors only values explicitly present in the selected managed material into Cura's supported top user layer. Plugin registration remains inert during Cura's plugin-loading phase: it must not construct the lazy machine manager or process active-machine state until Cura emits `initializationFinished`. At that signal it first replaces the Material Settings plugin's `visible_settings` preference with the complete server-supplied central catalog, then connects active-machine enforcement. This also reapplies the correct enabled setting list after an explicitly confirmed recovery restores Cura configuration. This keeps startup ordering safe and the material authoritative over both bundled and custom profiles without rewriting bundled Cura files. Non-material main-profile values such as layer-height, structural, support, adhesion, and special-purpose choices remain owned by Cura.

Managed material synchronization and takeover never change machine start G-code. The operator replaces only the existing Cura `START_PRINT` call with the documented `FILAMENT_MANAGER_START_PRINT ... MATERIAL_GUID={material_guid}` wrapper and preserves every other start/end line. An explicitly confirmed exact-version recovery restores the captured machine file, including its opaque start/end G-code. Product materials map to physical inventory; `Template <material type>` entries remain design-time starting points and intentionally have no eligible spool preflight mapping.

Known standard material fields use Cura's standard XML setting names. All other approved Cura and plugin values use `<cura:setting key="...">` within the material file. Pressure advance is `klipper_pressure_advance_factor`; the agent never injects `SET_PRESSURE_ADVANCE` itself.

## Operational Cura recovery

Recovery is separate from authoritative material synchronization. While Cura is closed, the agent captures bounded allowlisted printer, extruder, definition, variant, intent, quality, quality-change, visibility, user, and safe preference files plus a semantic installed-plugin inventory. The server retains the ten newest distinct points per workstation installation and Cura version. A missing printer or apparent reset/large deletion blocks the new capture and preserves the previous known-good point.

Recovery never uploads Cura account sessions, passwords, API keys, tokens, private endpoints, local filesystem paths, or plugin executable files. The browser receives recovery metadata and plugin names/versions, not raw configuration contents. Restores require an Administrator to select, review, and confirm an exact-version point. The originating agent waits for Cura to close, makes a local rollback archive, atomically replaces the allowlisted configuration, merges safe preferences while preserving the current excluded login and connection fields, and reports only a bounded path-free result. Normal material synchronization then restores Filament Manager's canonical templates and product materials.

The supported reset sequence is: install or reset the same Cura version, sign in to the Cura account and wait for its plugins to install, close Cura, confirm the recovery in Filament Manager, keep Cura closed until recovery reports Ready, and re-enter any excluded printer-service credentials. Plugin names and versions provide a verification checklist; Filament Manager does not install plugin binaries.

## Validation

- cooling minimum must not exceed maximum;
- fan values are 0-100;
- density and required speeds are positive;
- pressure advance is non-negative and bounded by the Cura Klipper Settings definition;
- extension keys must be in the approved catalog and match the expected boolean or numeric type;
- strings are bounded and may not contain newlines;
- preferred plate side must exist; and
- import never evaluates Cura expressions;
- request validation responses expose bounded field locations and reasons but never submitted values; and
- user quality-profile cleanup accepts only bounded regular files and central approved material keys; and
- recovery capture and restore accept only allowlisted regular files, exact reported Cura versions, bounded path-free payloads, and sanitized preferences/plugin metadata.

## Authoritative implementation references

- Cura Material Settings plugin: https://github.com/fieldOfView/Cura-MaterialSettingsPlugin
- Cura material XML serializer: https://github.com/Ultimaker/Cura/blob/main/plugins/XmlMaterialProfile/XmlMaterialProfile.py
- PostgreSQL documentation: https://www.postgresql.org/docs/
