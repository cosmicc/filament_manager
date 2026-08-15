# 10 - Cura Material Profiles and Settings

## Scope

Filament Manager presents directly saved material templates plus template-linked sparse product overrides. Internally it keeps complete immutable resolved snapshots for audit, exact print history, synchronization, and recovery. A workstation synchronization contains the current library for every matching template and product profile. It does not create quality-change profiles and does not patch machine start G-code.

Install and enable the Cura **Material Settings** plugin to expose the stored material values and the Cura **Klipper Settings** plugin to consume pressure advance and smooth time.

## Profile scope

A profile is scoped by filament product, printer, nozzle diameter, and optional layer-height range. It directly references the current template snapshot, stores only semantic differences from that base, and retains the resolved snapshot used by Cura. It may reference a preferred build-plate side such as `P4` or `P4b`.

## Approved Cura material catalog

The ordered implementation catalog is `CURA_MATERIAL_SETTINGS` in `src/filament_manager/domain/cura_material_settings.py`. It mirrors the operator's active Cura 5.13 Material Settings configuration.

- Temperature: `material_print_temperature`, `default_material_print_temperature`, `material_print_temperature_layer_0`, `material_initial_print_temperature`, `material_final_print_temperature`, `material_standby_temperature`, `material_bed_temperature`, `default_material_bed_temperature`, `material_bed_temperature_layer_0`, `build_volume_temperature`.
- Flow: `material_flow`, `material_flow_layer_0`, `infill_material_flow`, `support_material_flow`, `roofing_material_flow`, `skirt_brim_material_flow`.
- Speed: `speed_print`, `speed_print_layer_0`, `speed_layer_0`, `speed_wall`, `speed_wall_0`, `speed_wall_x`, `speed_infill`, `speed_topbottom`, `speed_roofing`, `speed_support`, `speed_travel`, `speed_travel_layer_0`, `skirt_brim_speed`, `cool_min_speed`.
- Retraction: `retraction_enable`, `retraction_amount`, `retraction_speed`, `retraction_retract_speed`, `retraction_prime_speed`, `retraction_min_travel`, `retract_at_layer_change`, `limit_support_retractions`.
- Cooling: `cool_fan_enabled`, `cool_fan_speed`, `cool_fan_speed_0`, `cool_fan_speed_min`, `cool_fan_speed_max`, `cool_fan_full_layer`, `cool_min_layer_time`, `cool_min_layer_time_fan_speed_max`.
- Geometry and support: `xy_offset`, `xy_offset_layer_0`, `hole_xy_offset`, `hole_xy_offset_max_diameter`, `support_angle`.
- Cura Klipper Settings: `klipper_pressure_advance_factor`, `klipper_smooth_time_enable`, `klipper_smooth_time_factor`.
- Derived read-only material metadata: `material_brand`, `material_type`.

Frequently used settings have typed PostgreSQL columns. Remaining approved settings use versioned `cura_extensions` JSONB. Arbitrary or machine-level Cura keys are rejected.

## Existing-source import

Each paired workstation scans bounded Cura material files with a hardened XML parser and saved `quality_changes` print-profile files with a non-interpolating INI parser. A saved profile's global and position-zero extruder layers are merged, with explicit extruder values winning. Only literal values from the approved tracked catalog are reported; expressions, unsupported keys, machine settings, additional extruders, and absolute paths are omitted. Discovery never modifies the local material or print profile.

Before takeover, Cura Workstations lists every discovered source beside a selector containing the existing active Filament Manager templates plus **Do not import**. An Administrator may map any subset, and each source and template may be used at most once in the batch. The review shows every selected source-to-template mapping and the number of ignored sources. One **Complete takeover** confirmation applies all mapped literal settings to those templates, cascades normal inheritance to their linked filament profiles, records provenance, enables management, and queues synchronization in one transaction.

Unmapped sources do not create templates or filament profiles and are removed from the managed Cura library only after the workstation backup is complete. The entire takeover is atomic: a stale agent report, unavailable template, duplicate source/template choice, or any failed save leaves management disabled and saves none of the mappings. A clean installation follows the same review and may complete with zero mappings.

After takeover, the workstation agent separately reports approved settings from Filament Manager-prefixed files with known deterministic GUIDs. A semantic change to a known template or product material saves directly and idempotently as the current state, then queues a full-library synchronization. Unknown GUIDs, copied/new Cura materials, metadata edits, and machine settings never create application records; new templates and products can be added only in Filament Manager.

## Template and product lifecycle

Templates are scoped to one printer and nozzle and synchronize to Cura with the exact name `Template <material type>` and brand `Template`. Creating or editing a template saves it immediately and queues a new complete-library checksum for every managed workstation. A new filament product receives a current linked profile containing only differences from its template. Saving a template immediately creates a new current resolved snapshot for every linked filament. Explicitly customized keys remain owned by that filament—even when their value temporarily equals the updated template—while all other keys inherit the new value.

Selecting a filament opens its canonical detail, linked template, inherited/customized count, and complete resolved Cura settings editor. Each field identifies its template value; **Reset to Template** removes that explicit customization on save. Saving takes effect immediately and automatically queues Cura synchronization. Applying calibration results starts from the session baseline and records calibrated differences without duplicating unrelated inherited values.

## Internal snapshot lifecycle

- draft
- calibration in progress
- validated
- published
- superseded
- archived

These status values remain an internal compatibility and history mechanism. Current template/profile snapshots are immutable once created, but the web interface exposes only direct saves and the current state. It never asks an operator to create a revision, publish a draft, or manually deploy Cura settings.

## Synchronization and export

The JSON export includes the semantic profile, complete computed Cura setting map, checksum, version, and deterministic managed material GUID. The workstation agent writes that GUID into Cura XML so `{material_guid}` identifies the exact current product profile during Klipper print preflight. It matches printer/nozzle entries, waits for Cura to close, backs up the union of existing and desired user material/plugin targets, atomically applies the exact desired state, removes stale user materials, and retains an idempotent rollback manifest. A managed Cura plugin filters selectors to `filament_manager_` material roots, hiding bundled choices without changing Cura's installation files.

The agent never changes machine start G-code. The operator replaces only the existing Cura `START_PRINT` call with the documented `FILAMENT_MANAGER_START_PRINT ... MATERIAL_GUID={material_guid}` wrapper and preserves every other start/end line. Product materials map to physical inventory; `Template <material type>` entries remain design-time starting points and intentionally have no eligible spool preflight mapping.

Known standard material fields use Cura's standard XML setting names. All other approved Cura and plugin values use `<cura:setting key="...">` within the material file. Pressure advance is `klipper_pressure_advance_factor`; the agent never injects `SET_PRESSURE_ADVANCE` itself.

## Validation

- cooling minimum must not exceed maximum;
- fan values are 0-100;
- density and required speeds are positive;
- pressure advance is non-negative and bounded by the Cura Klipper Settings definition;
- extension keys must be in the approved catalog and match the expected boolean or numeric type;
- strings are bounded and may not contain newlines;
- preferred plate side must exist; and
- import never evaluates Cura expressions.

## Authoritative implementation references

- Cura Material Settings plugin: https://github.com/fieldOfView/Cura-MaterialSettingsPlugin
- Cura material XML serializer: https://github.com/Ultimaker/Cura/blob/main/plugins/XmlMaterialProfile/XmlMaterialProfile.py
- PostgreSQL documentation: https://www.postgresql.org/docs/
