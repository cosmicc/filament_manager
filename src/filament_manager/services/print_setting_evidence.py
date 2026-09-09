"""Source-labelled presentation of retained print settings; no live lookups."""

from decimal import Decimal, InvalidOperation

from filament_manager.models.printing import PrintJob

SUMMARY_SETTING_KEYS = (
    "bed_temp_c",
    "initial_bed_temp_c",
    "extruder_temp_c",
    "chamber_temp_c",
    "print_speed_mm_s",
    "flow_percent",
    "retraction_distance_mm",
    "retraction_speed_mm_s",
    "pressure_advance",
)


def retained_setting_summary(job: PrintJob) -> dict[str, object]:
    """Fill absent summary values only from this print's immutable profile.

    These fallbacks describe the captured app request, not measured machine
    behavior. In particular they never become G-code inspection evidence.
    """
    sources: dict[str, str] = {}
    updates: dict[str, object] = {"setting_sources": sources}
    for key in SUMMARY_SETTING_KEYS:
        if getattr(job, key) is not None:
            sources[key] = "recorded_print"
            continue
        raw = job.profile_snapshot.get(key)
        if isinstance(raw, bool) or not isinstance(raw, str | int | float | Decimal):
            continue
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            continue
        if value.is_finite() and 0 <= value <= Decimal("1000000000"):
            updates[key] = value
            sources[key] = "captured_profile"
    return updates
