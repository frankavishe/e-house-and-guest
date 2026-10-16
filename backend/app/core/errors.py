"""Error model (contracts/rest-api.md): `{"error": {code, message, details}}`.

Business code raises `AppError`; the handlers below turn every failure into that shape with
a message localized from `Accept-Language`.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.i18n import normalize_locale, t

log = logging.getLogger(__name__)

_STATUS_CODES: dict[int, str] = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


class AppError(Exception):
    """A business error with a stable code. `message` overrides the catalog text."""

    def __init__(
        self,
        code: str,
        status: int = 400,
        details: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.details = details or {}
        self.message = message


# Convenience constructors for the common cases.
def not_found(what: str | None = None) -> AppError:
    return AppError("NOT_FOUND", 404, {"resource": what} if what else None)


def forbidden() -> AppError:
    return AppError("FORBIDDEN", 403)


def unauthenticated() -> AppError:
    return AppError("UNAUTHENTICATED", 401)


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _locale(request: Request) -> str:
    return normalize_locale(request.headers.get("accept-language"))


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    message = exc.message or t(f"errors.{exc.code}", _locale(request), **exc.details)
    headers = (
        {"Retry-After": str(exc.details["retry_after"])} if "retry_after" in exc.details else None
    )
    return JSONResponse(error_body(exc.code, message, exc.details), exc.status, headers=headers)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = [
        {
            "loc": [str(p) for p in err.get("loc", ())],
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    message = t("errors.VALIDATION_ERROR", _locale(request))
    return JSONResponse(error_body("VALIDATION_ERROR", message, {"fields": fields}), 422)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_CODES.get(exc.status_code, "INTERNAL_ERROR")
    message = t(f"errors.{code}", _locale(request))
    return JSONResponse(
        error_body(code, message), exc.status_code, headers=getattr(exc, "headers", None)
    )


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        error_body("INTERNAL_ERROR", t("errors.INTERNAL_ERROR", _locale(request))), 500
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)
