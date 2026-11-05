"""TypeVector Arena — RFC 7807 Problem Details Error Hierarchy and Handlers."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from typevector.middleware import get_current_request_id


class AppError(Exception):
    """Base application exception supporting RFC 7807 Problem Details."""

    def __init__(
        self,
        status_code: int = 500,
        title: str = "Internal Server Error",
        detail: str = "An unexpected error occurred.",
        code: str = "INTERNAL_SERVER_ERROR",
        error_type: str = "https://typevector.arena/errors/internal",
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.code = code
        self.error_type = error_type
        self.errors = errors or []

    def to_problem_dict(self, instance: str) -> dict[str, Any]:
        """Convert exception to RFC 7807 Problem Details representation."""
        result: dict[str, Any] = {
            "type": self.error_type,
            "title": self.title,
            "status": self.status_code,
            "detail": self.detail,
            "instance": instance,
            "code": self.code,
            "request_id": get_current_request_id(),
        }
        if self.errors:
            result["errors"] = self.errors
        return result


class EntityNotFoundError(AppError):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        entity: str,
        identifier: Any,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            status_code=404,
            title="Entity Not Found",
            detail=detail or f"{entity} with identifier '{identifier}' was not found.",
            code="ENTITY_NOT_FOUND",
            error_type="https://typevector.arena/errors/not-found",
        )


class ConflictError(AppError):
    """Raised when an action conflicts with current state or invariant."""

    def __init__(
        self,
        detail: str,
        code: str = "CONFLICT",
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            status_code=409,
            title="State Conflict",
            detail=detail,
            code=code,
            error_type="https://typevector.arena/errors/conflict",
            errors=errors,
        )


class UnauthorizedError(AppError):
    """Raised when authentication is missing or invalid."""

    def __init__(self, detail: str = "Authentication required.") -> None:
        super().__init__(
            status_code=401,
            title="Unauthorized",
            detail=detail,
            code="UNAUTHORIZED",
            error_type="https://typevector.arena/errors/unauthorized",
        )


class ForbiddenError(AppError):
    """Raised when the authenticated caller lacks required permission."""

    def __init__(self, detail: str = "Permission denied.") -> None:
        super().__init__(
            status_code=403,
            title="Forbidden",
            detail=detail,
            code="FORBIDDEN",
            error_type="https://typevector.arena/errors/forbidden",
        )


class InvariantViolationError(AppError):
    """Raised when a business domain invariant is violated."""

    def __init__(self, detail: str, code: str = "INVARIANT_VIOLATION") -> None:
        super().__init__(
            status_code=422,
            title="Domain Invariant Violation",
            detail=detail,
            code=code,
            error_type="https://typevector.arena/errors/invariant-violation",
        )


def register_error_handlers(app: FastAPI) -> None:
    """Register RFC 7807 Problem Details exception handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_problem_dict(instance=request.url.path),
            headers={"Content-Type": "application/problem+json"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        problem = {
            "type": "https://typevector.arena/errors/validation-failed",
            "title": "Validation Failed",
            "status": 422,
            "detail": "Request payload failed validation schema.",
            "instance": request.url.path,
            "code": "VALIDATION_FAILED",
            "request_id": get_current_request_id(),
            "errors": errors,
        }
        return JSONResponse(
            status_code=422,
            content=problem,
            headers={"Content-Type": "application/problem+json"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        problem = {
            "type": f"https://typevector.arena/errors/http-{exc.status_code}",
            "title": exc.detail if isinstance(exc.detail, str) else "HTTP Error",
            "status": exc.status_code,
            "detail": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "instance": request.url.path,
            "code": f"HTTP_{exc.status_code}",
            "request_id": get_current_request_id(),
        }
        return JSONResponse(
            status_code=exc.status_code,
            content=problem,
            headers={"Content-Type": "application/problem+json"},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        import traceback

        problem = {
            "type": "https://typevector.arena/errors/internal",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected server error occurred. Inspect request_id for details.",
            "instance": request.url.path,
            "code": "INTERNAL_SERVER_ERROR",
            "request_id": get_current_request_id(),
        }
        # In non-production, include error message
        if not request.app.debug:
            # log full traceback with request_id
            from typevector.logging import logger

            logger.error(
                f"Unhandled exception [req_id={get_current_request_id()}]: {exc}\n{traceback.format_exc()}"
            )
        else:
            problem["debug_error"] = str(exc)

        return JSONResponse(
            status_code=500,
            content=problem,
            headers={"Content-Type": "application/problem+json"},
        )
