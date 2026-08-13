"""Audit-event correlation identifier safety tests."""

from filament_manager.services.events import bounded_correlation_id


def test_long_correlation_identifiers_are_bounded_and_stable() -> None:
    """Internal worker context cannot exceed the database's 64-character contract."""

    first = "automatic:" + "a" * 120 + ":active-spool"
    second = "automatic:" + "a" * 120 + ":printer-info"

    assert len(bounded_correlation_id(first)) == 64
    assert bounded_correlation_id(first) == bounded_correlation_id(first)
    assert bounded_correlation_id(first) != bounded_correlation_id(second)
    assert bounded_correlation_id("request-123") == "request-123"
