"""Error model (contracts/rest-api.md): `{"error": {code, message, details}}`.

Business code raises `AppError`; the handlers below turn every failure into that shape with
a message localized from `Accept-Language`.
"""

import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.i18n import normalize_locale, t

log = logging.getLogger(__name__)

_STATUS_CODES: dict[int, str] = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
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


PHONE_FIELDS = {"phone", "msisdn"}


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
    # A malformed phone gets its own code so clients can show the "Tanzanian number" hint.
    code = (
        "INVALID_PHONE"
        if fields and all(f["loc"] and f["loc"][-1] in PHONE_FIELDS for f in fields)
        else "VALIDATION_ERROR"
    )
    message = t(f"errors.{code}", _locale(request))
    return JSONResponse(error_body(code, message, {"fields": fields}), 422)


_HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head"}


def _allowed_methods(request: Request) -> str:
    """Methods documented for this path in the OpenAPI document. (FastAPI registers one
    route per method, so Starlette's own `Allow` header lists only one of them.)"""
    path = request.url.path
    methods: set[str] = set()
    for template, item in request.app.openapi().get("paths", {}).items():
        pattern = "^" + re.sub(r"\\{[^}]+\\}", "[^/]+", re.escape(template)) + "$"
        if re.match(pattern, path):
            methods |= {m.upper() for m in item if m in _HTTP_METHODS}
    return ", ".join(sorted(methods))


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_CODES.get(exc.status_code, "INTERNAL_ERROR")
    message = t(f"errors.{code}", _locale(request))
    headers = dict(getattr(exc, "headers", None) or {})
    if exc.status_code == 405:
        headers["Allow"] = _allowed_methods(request)
    return JSONResponse(error_body(code, message), exc.status_code, headers=headers or None)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        error_body("INTERNAL_ERROR", t("errors.INTERNAL_ERROR", _locale(request))), 500
    )


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any]


class ErrorResponse(BaseModel):
    """Every non-2xx response: `{"error": {code, message, details}}`."""

    error: ErrorBody


def _error_ref() -> dict[str, Any]:
    return {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}


def install_error_openapi(app: FastAPI) -> None:
    """Document the error envelope: 422 replaces FastAPI's default validation schema, and
    `default` covers the other error statuses (401/403/404/409/429…)."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title, version=app.version, routes=app.routes, description=app.description
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.update(
            {
                name: definition
                for name, definition in ErrorResponse.model_json_schema(
                    ref_template="#/components/schemas/{model}"
                )
                .get("$defs", {})
                .items()
            }
        )
        error_schema = ErrorResponse.model_json_schema(ref_template="#/components/schemas/{model}")
        error_schema.pop("$defs", None)
        components["ErrorResponse"] = error_schema
        components.pop("HTTPValidationError", None)
        components.pop("ValidationError", None)
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                responses = operation.setdefault("responses", {})
                if "422" in responses:
                    responses["422"] = {"description": "Validation error", "content": _error_ref()}
                for status, response in responses.items():
                    if status.startswith(("4", "5")) and "content" not in response:
                        response["content"] = _error_ref()
                responses.setdefault("default", {"description": "Error", "content": _error_ref()})
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)
