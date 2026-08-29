"""Read-only Print History route behavior tests."""

from typing import Any

import pytest

from filament_manager.api.routes import printing


class _EmptyScalarResult:
    """Minimal SQLAlchemy scalar-result stand-in for an empty print page."""

    def unique(self) -> "_EmptyScalarResult":
        return self

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(())


class _EmptyResult:
    def scalars(self) -> _EmptyScalarResult:
        return _EmptyScalarResult()


class _PageSession:
    def __init__(self, total_items: int) -> None:
        self.total_items = total_items
        self.executed_query: Any = None

    async def scalar(self, _query: object) -> int:
        return self.total_items

    async def execute(self, query: object) -> _EmptyResult:
        self.executed_query = query
        return _EmptyResult()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("per_page", "expected_total_pages", "expected_page"),
    [(10, 3, 3), (25, 1, 1), (50, 1, 1), (100, 1, 1)],
)
async def test_print_page_clamps_to_last_page_and_returns_exact_totals(
    per_page: int,
    expected_total_pages: int,
    expected_page: int,
) -> None:
    """A stale browser page remains bounded after filtered history shrinks."""

    session = _PageSession(total_items=23)

    response = await printing.list_print_page(  # type: ignore[arg-type]
        None,
        session,
        page=99,
        per_page=per_page,  # type: ignore[arg-type]
    )

    assert response.page == expected_page
    assert response.per_page == per_page
    assert response.total_items == 23
    assert response.total_pages == expected_total_pages
    assert response.items == []
    assert session.executed_query is not None
