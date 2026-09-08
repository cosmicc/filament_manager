"""Bounded independent-hotend identities; physical movement remains printer-owned."""

EXTRUDERS = tuple("extruder" if index == 0 else f"extruder{index}" for index in range(16))


def extruder_name(value: object, count: int) -> str:
    """Require an explicit slot on multi-hotend printers, never guess a tool."""

    if value is None and count == 1:
        return "extruder"
    if not isinstance(value, str) or value not in EXTRUDERS[:count]:
        raise ValueError("Select one configured hotend")
    return str(value)


def tool_number(value: str) -> int:
    """Translate only known canonical slots into safe T-number commands."""

    return EXTRUDERS.index(value)
