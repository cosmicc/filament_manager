"""Render the narrow, in-memory AutoTowers speed compatibility adapter.

This independently implemented adapter wraps the installed processor, not its
files. Keep it separate from material enforcement: it never changes app values.
"""

AUTOTOWERS_COMPATIBILITY_CODE = r'''
# AutoTowers speed processor 4.1 changes base retractions to start minus step.
# Preserve the slicer's original positive feeds before that processor runs;
# restore only exact, recognized changes before its export callback returns.
import inspect
import sys
from decimal import Decimal, InvalidOperation
from functools import wraps

AUTOTOWERS_SPEED_MODULE = "AutoTowersGenerator.Postprocessing.RetractSpeedTower_PostProcessing"
AUTOTOWERS_PARAMETERS = (
    "gcode", "base_height", "section_height", "initial_layer_height", "layer_height",
    "start_retract_speed", "retract_speed_change", "enable_lcd_messages",
    "enable_advanced_gcode_comments",
)
AUTOTOWERS_PREFIX_LIMIT = 8 * 1024 * 1024
AUTOTOWERS_LINE_LIMIT = 64 * 1024
AUTOTOWERS_MOVE_LIMIT = 100000
AUTOTOWERS_NUMBER = r"[-+]?[0-9]*\.?[0-9]+"
AUTOTOWERS_MOVE = re.compile(
    r"[ \t]*G1[ \t]+(?:F(" + AUTOTOWERS_NUMBER + r")[ \t]+E" + AUTOTOWERS_NUMBER
    + r"|E" + AUTOTOWERS_NUMBER + r"[ \t]+F(" + AUTOTOWERS_NUMBER + r"))[ \t]*(?:;[^\r\n]*)?\r?"
)
AUTOTOWERS_CORRECTION_MARKER = (
    ";FilamentManager: Preserved original base retract/prime speeds before AutoTowers speed sections."
)


def _autotowers_warning():
    """Report unsupported input without logging G-code, paths, or user values."""

    Logger.log("w", "Filament Manager could not verify the AutoTowers base-speed correction")
    try:
        from UM.Message import Message
        Message(
            "The AutoTowers base-speed correction could not be verified. "
            "Do not print this tower until its G-code has been checked for invalid speeds.",
            title="Filament Manager",
            message_type=Message.MessageType.WARNING,
        ).show()
    except Exception:
        # Optional UI reporting must not break Cura's material initialization.
        Logger.log("w", "Filament Manager could not display the AutoTowers compatibility warning")


def _autotowers_base_moves(arguments):
    """Capture bounded positive E-only feeds strictly before the first test section.

    Match the supported processor's decimal layer-height boundary, including its
    exclusion of TIME_ELAPSED tails. Do not infer speed from E's sign: absolute
    extrusion and differing retract/prime speeds must both remain correct.
    """

    gcode = arguments["gcode"]
    if not isinstance(gcode, list) or not gcode:
        return None
    try:
        base, section, initial, layer = (
            Decimal(str(arguments[key])) for key in (
                "base_height", "section_height", "initial_layer_height", "layer_height"
            )
        )
        if not all(value.is_finite() for value in (base, section, initial, layer)):
            return None
        if base < 0 or min(section, initial, layer) <= 0:
            return None
    except (InvalidOperation, TypeError, ValueError):
        return None
    height = Decimal(0)
    scanned = 0
    moves = []
    for clump_index, clump in enumerate(gcode):
        if not isinstance(clump, str):
            return None
        scanned += len(clump)
        if scanned > AUTOTOWERS_PREFIX_LIMIT:
            return None
        for line_index, line in enumerate(clump.split("\n")):
            if len(line) > AUTOTOWERS_LINE_LIMIT:
                return None
            if line.strip().startswith(";TIME_ELAPSED:"):
                break
            if re.match(r";LAYER:[0-9]+\s*", line):
                height += initial if height == 0 else layer
                if height > base:
                    return moves
            match = AUTOTOWERS_MOVE.fullmatch(line)
            if match is None:
                continue
            feed = match.group(1) or match.group(2)
            if len(feed) > 64 or Decimal(feed) <= 0:
                continue
            moves.append((clump_index, line_index, line, feed))
            if len(moves) > AUTOTOWERS_MOVE_LIMIT:
                return None
    # Without an actual first section we cannot establish a calibration boundary.
    return None


def _autotowers_restore_base(result, moves, arguments):
    """Restore only the exact speed-only edits made by the recognized processor.

    Stage every replacement before applying any. Unexpected line movement or
    changed extrusion content is not permission to guess at a repair.
    """

    if not isinstance(result, list):
        return False
    base_speed = arguments["start_retract_speed"] - arguments["retract_speed_change"]
    base_feed = str(int(base_speed * 60))
    suffix = ""
    if arguments["enable_advanced_gcode_comments"]:
        suffix = (
            f" ;AutoTowersGenerator: Changed retraction speed to {base_speed} mm/s "
            f"({base_speed * 60} mm/min)"
        )
    changed_clumps = {}
    restored = 0
    for clump_index, line_index, original, feed in moves:
        if clump_index >= len(result) or not isinstance(result[clump_index], str):
            return False
        if clump_index not in changed_clumps:
            changed_clumps[clump_index] = result[clump_index].split("\n")
        lines = changed_clumps[clump_index]
        if line_index >= len(lines):
            return False
        current = lines[line_index]
        if current == original:
            continue
        expected = original.replace("F" + feed, "F" + base_feed) + suffix
        if current != expected:
            return False
        lines[line_index] = original
        restored += 1
    for clump_index, lines in changed_clumps.items():
        result[clump_index] = "\n".join(lines)
    if restored:
        if AUTOTOWERS_CORRECTION_MARKER not in result[0]:
            result[0] += "\n" + AUTOTOWERS_CORRECTION_MARKER + "\n"
        Logger.log("i", "Filament Manager preserved AutoTowers base retract/prime speeds")
    return True


def _wrap_autotowers_speed_processor(original):
    """Intercept the processor itself so export-signal ordering cannot race us."""

    signature = inspect.signature(original)

    @wraps(original)
    def process(*args, **kwargs):
        arguments = signature.bind(*args, **kwargs).arguments
        moves = _autotowers_base_moves(arguments)
        result = original(*args, **kwargs)
        if moves is None or not _autotowers_restore_base(result, moves, arguments):
            _autotowers_warning()
        return result

    process._filament_manager_base_speed_patch = True
    return process


def _install_autotowers_compatibility():
    """Wrap only the loaded, recognized optional plugin after Cura initialization.

    Never import or rewrite a third-party plugin, patch G1 globally, add printer
    traffic, or attach another output-device signal with uncertain ordering.
    """

    module = sys.modules.get(AUTOTOWERS_SPEED_MODULE)
    if module is None:
        return
    original = getattr(module, "execute", None)
    if getattr(original, "_filament_manager_base_speed_patch", False):
        return
    try:
        if (
            getattr(module, "__version__", None) != "4.1"
            or not callable(original)
            or tuple(inspect.signature(original).parameters) != AUTOTOWERS_PARAMETERS
        ):
            _autotowers_warning()
            return
        module.execute = _wrap_autotowers_speed_processor(original)
    except (TypeError, ValueError):
        _autotowers_warning()
'''
