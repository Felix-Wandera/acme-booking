from typing import Any, Dict
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException


def format_error_response(code: str, message: str, status_code: int) -> JSONResponse:
    """Format an error payload into the uniform system error schema."""
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": {
                "code": code,
                "message": message,
            }
        },
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle domain business-logic exceptions with structured error codes."""
    return format_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Normalize FastAPI and Pydantic validation errors into the standard error format."""
    errors = exc.errors()
    if errors:
        first_err = errors[0]
        loc = " -> ".join(str(p) for p in first_err.get("loc", []) if p != "body")
        msg = first_err.get("msg", "Invalid value.")
        formatted_msg = f"{loc}: {msg}" if loc else msg
    else:
        formatted_msg = "Request validation failed."

    return format_error_response(
        code="VALIDATION_ERROR",
        message=formatted_msg,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Handle generic Starlette HTTP exceptions (404, 405, etc.)."""
    code_map = {
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    message = str(exc.detail) if exc.detail else "An HTTP error occurred."

    return format_error_response(
        code=code,
        message=message,
        status_code=exc.status_code,
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI application instance."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
