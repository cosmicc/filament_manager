"""Constant-memory observations from the already downloaded G-code stream."""

import re
from decimal import Decimal

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"


class GcodeObservations:
    """Track heater maxima and deposited layer heights without executing G-code."""

    def __init__(self) -> None:
        self.pending = b""
        self.discard = False
        self.values: dict[str, object] = {}
        self.z = Decimal(0)
        self.e = Decimal(0)
        self.absolute_xyz = True
        self.absolute_e = True
        self.layer_pending = False
        self.last_layer_z: Decimal | None = None

    def feed(self, chunk: bytes) -> None:
        """Consume chunks with bounded line storage, including split commands."""
        for index, part in enumerate(chunk.split(b"\n")):
            if index:
                if not self.discard:
                    self.line(self.pending.decode("utf-8", errors="replace"))
                self.pending = b""
                self.discard = False
            if not self.discard:
                if len(self.pending) + len(part) > 4096:
                    self.pending = b""
                    self.discard = True
                else:
                    self.pending += part

    def finish(self) -> dict[str, object]:
        """Return only bounded numeric observations suitable for retained evidence."""
        self.feed(b"\n")
        return self.values

    def maximum(self, key: str, value: Decimal) -> None:
        """Retain unsafe high targets rather than dropping out-of-range evidence."""
        if value >= 0:
            # Above every supported printer limit; bound hostile numeric output
            # without turning an absurdly high heater target into missing evidence.
            value = min(value, Decimal(2000))
            self.values[key] = str(max(value, Decimal(str(self.values.get(key, 0)))))

    def line(self, raw: str) -> None:
        """Observe supported heater commands and Cura layer deposition boundaries."""
        if re.fullmatch(r";LAYER:\s*\d+\s*", raw):
            self.layer_pending = True
        code = raw.split(";", 1)[0].strip().upper()
        if not code:
            return
        command = code.split()[0]
        params = {
            key: Decimal(value) for key, value in re.findall(rf"\b([XYZESTR])\s*({NUMBER})(?=\s|$)", code)
        }
        heater = {
            "M104": "extruder",
            "M109": "extruder",
            "M140": "bed",
            "M190": "bed",
            "M141": "chamber",
            "M191": "chamber",
        }.get(command)
        if heater:
            for key in ("S", "R"):
                if key in params:
                    self.maximum(f"maximum_{heater}_temp_c", params[key])
        if command in {"FILAMENT_MANAGER_START_PRINT", "START_PRINT", "SET_HEATER_TEMPERATURE"}:
            named = dict(re.findall(rf"\b([A-Z_]+)=({NUMBER})(?=\s|$)", code))
            for key, group in (
                ("BED_TEMP", "bed"),
                ("REGULAR_BED_TEMP", "bed"),
                ("EXTRUDER_TEMP", "extruder"),
                ("CHAMBER_TEMP", "chamber"),
            ):
                if key in named:
                    self.maximum(f"maximum_{group}_temp_c", Decimal(named[key]))
            if command == "SET_HEATER_TEMPERATURE" and "TARGET" in named:
                match = re.search(r"\bHEATER=(EXTRUDER\d*|HEATER_BED|CHAMBER)\b", code)
                if match:
                    group = (
                        "extruder"
                        if match[1].startswith("EXTRUDER")
                        else "bed"
                        if match[1] == "HEATER_BED"
                        else "chamber"
                    )
                    self.maximum(f"maximum_{group}_temp_c", Decimal(named["TARGET"]))
        if command in {"G90", "G91"}:
            self.absolute_xyz = command == "G90"
        elif command in {"M82", "M83"}:
            self.absolute_e = command == "M82"
        elif command == "G92":
            self.e = params.get("E", self.e)
            self.z = params.get("Z", self.z)
        elif command in {"G0", "G1", "G2", "G3"}:
            if "Z" in params:
                self.z = params["Z"] if self.absolute_xyz else self.z + params["Z"]
            deposited = "E" in params and (params["E"] > self.e if self.absolute_e else params["E"] > 0)
            if "E" in params:
                self.e = params["E"] if self.absolute_e else self.e + params["E"]
            if self.layer_pending and deposited and ("X" in params or "Y" in params):
                height = self.z - (self.last_layer_z or Decimal(0))
                if 0 < height <= 10:
                    if self.last_layer_z is None:
                        self.values["initial_layer_height_mm"] = str(height)
                    else:
                        minimum = Decimal(str(self.values.get("minimum_layer_height_mm", height)))
                        maximum = Decimal(str(self.values.get("maximum_layer_height_mm", height)))
                        self.values["minimum_layer_height_mm"] = str(min(minimum, height))
                        self.values["maximum_layer_height_mm"] = str(max(maximum, height))
                    self.last_layer_z = self.z
                self.layer_pending = False
