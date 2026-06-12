from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Base class for typed API errors — mapped to a consistent error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


class Unauthorized(ApiError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


class AuthServiceUnavailable(ApiError):
    def __init__(self) -> None:
        super().__init__(503, "auth_unavailable", "Could not reach the signing key service")


class BadRequest(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(400, "bad_request", message)


class Forbidden(ApiError):
    def __init__(self, message: str = "Not allowed") -> None:
        super().__init__(403, "forbidden", message)


class NotFound(ApiError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(404, "not_found", message)


class Conflict(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(409, "conflict", message)


class QuotaExceeded(ApiError):
    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(
            429,
            "quota_exceeded",
            message,
            headers={"Retry-After": str(retry_after_seconds)},
        )
        self.retry_after_seconds = retry_after_seconds


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=exc.headers,
        )
