"""Authoritative Cura machine settings owned by Filament Manager."""

import configparser
import io

MANAGED_MACHINE_START_GCODE = (
    ";===== MOONRAKER METADATA =====\n"
    ";Nozzle diameter = {machine_nozzle_size}\n"
    ";Filament type = {material_type}\n"
    ";Filament name = {material_name}\n"
    ";Filament weight = {filament_weight}\n"
    ";M109 S{material_print_temperature}\n"
    ";M190 S{material_bed_temperature}\n"
    ";M191 S{build_volume_temperature}\n"
    ";===== END MOONRAKER METADATA =====\n"
    "FILAMENT_MANAGER_START_PRINT "
    "MATERIAL_GUID={material_guid, 0} "
    "BED_TEMP={material_bed_temperature_layer_0, 0} "
    "REGULAR_BED_TEMP={material_bed_temperature, 0} "
    "EXTRUDER_TEMP={material_print_temperature_layer_0, 0} "
    "CHAMBER_TEMP={build_volume_temperature}"
)
MANAGED_MACHINE_END_GCODE = "END_PRINT"


def apply_managed_machine_gcode(parser: configparser.ConfigParser) -> None:
    """Overwrite the saved Cura print boundaries in one validated machine document."""

    if not parser.has_section("values"):
        parser.add_section("values")
    parser["values"]["machine_start_gcode"] = MANAGED_MACHINE_START_GCODE
    parser["values"]["machine_end_gcode"] = MANAGED_MACHINE_END_GCODE


def serialize_cura_config(parser: configparser.ConfigParser) -> bytes:
    """Serialize one validated Cura INI document for an atomic local write."""

    output = io.StringIO()
    parser.write(output, space_around_delimiters=True)
    return output.getvalue().encode("utf-8")
