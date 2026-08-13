"""Stable API error responses."""

import structlog
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


class ApiError(HTTPException):
    """HTTP exception carrying a stable machine-readable error code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Render stable errors without exposing tracebacks or internal details."""

    logger.warning(
        "api_request_rejected",
        method=request.method,
        path=request.url.path,
        status=exc.status_code,
        error_code=exc.code,
        error=str(exc.detail),
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": str(exc.detail),
            "correlation_id": getattr(request.state, "correlation_id", None),
        },
    )
