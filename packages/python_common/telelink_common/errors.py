"""C01 safe error envelopes, including correlation and validation details."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException


class ErrorDetail(BaseModel):
    field: str
    code: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[ErrorDetail]


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class DomainError(HTTPException):
    def __init__(self, status: int, code: str, message: str, details: list | None = None):
        super().__init__(status, message)
        self.code = code
        self.details = details or []


def error_response(request, status, code, message, details=None, headers=None):
    request_id = request.state.request_id
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "details": details or [],
            }
        },
        status_code=status,
        headers={"X-Request-ID": request_id, **(headers or {})},
    )


def install_error_handlers(app):
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        codes = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 503: "unavailable"}
        return error_response(
            request,
            error.status_code,
            getattr(error, "code", codes.get(error.status_code, "bad_request")),
            error.detail,
            getattr(error, "details", []),
            error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        details = [
            {
                "field": ".".join(
                    str(part)
                    for part in (
                        item["loc"][:1] if item["type"] == "extra_forbidden" else item["loc"]
                    )
                ),
                "code": "invalid_value",
                "message": "Invalid field value.",
            }
            for item in error.errors()
        ]
        return error_response(
            request, 422, "validation_error", "One or more fields are invalid.", details
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, error: IntegrityError):
        return error_response(request, 409, "conflict", "The change conflicts with current data.")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        return error_response(request, 503, "unavailable", "Service storage is unavailable.")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        return error_response(request, 500, "internal_error", "An unexpected error occurred.")
