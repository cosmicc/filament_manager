# 10 - Cura Material Profiles and Settings

## Scope

Filament Manager stores versioned generic templates and product-owned Cura material settings. A workstation deployment is the complete latest published library for every matching template and product profile. It does not create quality-change profiles and does not patch machine start G-code.

Install and enable the Cura **Material Settings** plugin to expose the stored material values and the Cura **Klipper Settings** plugin to consume pressure advance and smooth time.

## Profile scope

A profile is scoped by filament product, printer, nozzle diameter, optional layer-height range, and version. It may reference a preferred build-plate side such as `P4` or `P4b`.

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

## Existing-material import

Each paired workstation scans bounded Cura material files with a hardened XML parser. It reports only the approved keys and semantic material labels; it never reports absolute paths. The Profiles page requires an explicit mapping to a canonical filament, printer/nozzle, and optional plate side before creating a draft. Import never modifies the local Cura material. Printing and bed temperatures must be present. When Cura omitted inherited flow or fan values from the material XML, import stores 100% flow, 100% maximum fan, and the maximum fan value as the minimum in the draft.

Import desired existing user materials before authoritative takeover. A clean user-material directory may enable management automatically. Otherwise, an Administrator must confirm that all user material files will be backed up and replaced.

## Template and product lifecycle

Generic templates are scoped to one printer and nozzle. Publishing a template revision makes it available to create products and adds it to the desired Cura library. A new filament product receives its own draft profile copied from that published revision; later template revisions do not rewrite already-tuned products. Publishing any template or product revision queues a new complete-library checksum for every managed workstation.

Selecting a filament opens its canonical detail and complete approved Cura settings editor. Saving settings always creates the next draft profile version; it never mutates a published snapshot. Calibration publication starts from the session's baseline profile and overlays measured results so unrelated template-derived settings are retained.

## Profile lifecycle

- draft
- calibration in progress
- validated
- published
- superseded
- archived

Published versions are immutable. A revision creates a new draft/version.

## Deployment and export

The JSON export includes the semantic profile, complete computed Cura setting map, checksum, and version. The workstation agent matches printer/nozzle entries, waits for Cura to close, backs up the union of existing and desired user material/plugin targets, atomically applies the exact desired state, removes stale user materials, and retains an idempotent rollback manifest. A managed Cura plugin filters selectors to `filament_manager_` material roots, hiding bundled choices without changing Cura's installation files.

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
