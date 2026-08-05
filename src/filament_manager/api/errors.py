"""Stable API error responses."""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    """HTTP exception carrying a stable machine-readable error code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Render stable errors without exposing tracebacks or internal details."""

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": str(exc.detail),
            "correlation_id": getattr(request.state, "correlation_id", None),
        },
    )
