"""FastAPI application factory and production entrypoint."""

import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text

from filament_manager import __version__
from filament_manager.api.errors import ApiError, api_error_handler
from filament_manager.api.router import api_router
from filament_manager.config import get_settings
from filament_manager.database import database_ready, get_engine, get_session_factory
from filament_manager.domain.cura_material_settings import CURA_EXTENSION_SETTING_KEYS
from filament_manager.logging import configure_logging
from filament_manager.services.accounts import ensure_single_administrator

REQUESTS = Counter("filament_manager_http_requests_total", "HTTP request count", ["method", "path", "status"])
LATENCY = Histogram(
    "filament_manager_http_request_duration_seconds", "HTTP request duration", ["method", "path"]
)
logger = structlog.get_logger()


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    """Return bounded field errors without echoing request values or validator context."""

    errors: list[dict[str, str]] = []
    for error in exc.errors():
        raw_location = error.get("loc", ())
        location = [
            str(part) for part in raw_location if part not in {"body", "query", "path", "header", "cookie"}
        ]
        raw_message = str(error.get("msg") or "The supplied value is invalid")
        message = raw_message.removeprefix("Value error, ")[:300]
        # Pydantic locates custom dictionary validation at the dictionary itself.
        # Narrow approved Cura-extension failures to the exact safe catalog key
        # named by the validator so the UI can annotate the correct control.
        if location and location[-1] == "cura_extensions":
            matched_key = next(
                (
                    key
                    for key in sorted(CURA_EXTENSION_SETTING_KEYS)
                    if re.search(rf"(?<![a-z0-9_]){re.escape(key)}(?![a-z0-9_])", message)
                ),
                None,
            )
            if matched_key is not None:
                location.append(matched_key)
        errors.append(
            {
                "field": ".".join(location) or "request",
                "message": message,
                "type": str(error.get("type") or "value_error")[:96],
            }
        )
    return errors[:100]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Configure logging and dispose pooled connections on shutdown."""

    settings = get_settings()
    configure_logging(settings.app.log_level)
    settings.app.data_dir.mkdir(parents=True, exist_ok=True)
    async with get_session_factory()() as session:
        created = await ensure_single_administrator(session)
        if created:
            logger.warning("default_administrator_created", username="admin", password_change_required=True)
    logger.info("application_started", version=__version__)
    yield
    await get_engine().dispose()
    logger.info("application_stopped")


def create_app() -> FastAPI:
    """Create the configured ASGI application."""

    settings = get_settings()
    app = FastAPI(
        title="Filament Manager API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.app.allowed_hosts)
    if settings.app.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin).rstrip("/") for origin in settings.app.cors_origins],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-ID"],
        )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = request.headers.get("X-Request-ID", "")[:64] or str(uuid4())
        request.state.correlation_id = correlation_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed", method=request.method, path=request.url.path)
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "code": "internal_error",
                    "message": "The request could not be completed",
                    "correlation_id": correlation_id,
                },
            )
        elapsed = time.monotonic() - start
        route = request.scope.get("route")
        path_label = getattr(route, "path", "unmatched")
        REQUESTS.labels(request.method, path_label, response.status_code).inc()
        LATENCY.labels(request.method, path_label).observe(elapsed)
        logger.info(
            "http_request_completed",
            method=request.method,
            path=request.url.path,
            route=path_label,
            status=response.status_code,
            duration_ms=round(elapsed * 1000, 2),
        )
        response.headers["X-Request-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        safe_errors = _safe_validation_errors(exc)
        logger.warning(
            "request_validation_failed",
            method=request.method,
            path=request.url.path,
            error_count=len(safe_errors),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "validation_error",
                "message": "Request validation failed",
                "errors": safe_errors,
                "correlation_id": request.state.correlation_id,
            },
        )

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        if not await database_ready():
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        try:
            async with get_engine().connect() as connection:
                version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "schema_unavailable"})
        return JSONResponse(content={"status": "ready", "schema_version": version})

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(api_router)

    static_dir = settings.app.static_dir
    if static_dir.is_dir():
        assets = static_dir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa_fallback(path: str) -> FileResponse:
            requested = (static_dir / path).resolve()
            if requested.is_relative_to(static_dir.resolve()) and requested.is_file():
                return FileResponse(requested)
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()


def run() -> None:
    """Run the production server with one process-managed worker."""

    # The container entrypoint listens on its network namespace. Published ports remain operator-controlled.
    uvicorn.run(
        "filament_manager.main:app",
        host="0.0.0.0",  # noqa: S104
        port=8080,
        proxy_headers=False,
    )
