"""Read-only Print History route behavior tests."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from filament_manager.api import dependencies
from filament_manager.api.errors import ApiError, api_error_handler
from filament_manager.api.routes import printing
from filament_manager.models.enums import UserRole


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


def _http_test_app(session: _PageSession) -> FastAPI:
    """Build the smallest authenticated app that exercises real query parsing."""

    async def session_override() -> AsyncIterator[_PageSession]:
        yield session

    async def user_override() -> SimpleNamespace:
        return SimpleNamespace(role=UserRole.VIEWER)

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
    app.include_router(printing.router, prefix="/api/v1")
    app.dependency_overrides[dependencies.session_dependency] = session_override
    app.dependency_overrides[dependencies.current_user] = user_override
    return app


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
    assert "print_settings_snapshot" not in str(session.executed_query)


@pytest.mark.asyncio
async def test_print_page_accepts_browser_query_string_page_size() -> None:
    """The real HTTP route must parse a browser's numeric query string."""

    session = _PageSession(total_items=23)
    app = _http_test_app(session)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/prints/page?page=1&per_page=10")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "page": 1,
        "per_page": 10,
        "total_items": 23,
        "total_pages": 3,
    }


@pytest.mark.asyncio
async def test_print_page_accepts_printer_filter() -> None:
    """Printer selection narrows both the count and the returned page query."""

    session = _PageSession(total_items=0)
    app = _http_test_app(session)
    printer_id = uuid4()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/prints/page?printer_id={printer_id}")

    assert response.status_code == 200
    assert session.executed_query is not None
    assert "print_jobs.printer_id" in str(session.executed_query)


@pytest.mark.asyncio
async def test_print_page_rejects_unsupported_page_size() -> None:
    """Only the four documented bounded page sizes are accepted."""

    session = _PageSession(total_items=23)
    app = _http_test_app(session)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/prints/page?page=1&per_page=20")

    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_print_page_size"
