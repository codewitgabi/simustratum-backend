from fastapi import Request, status, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException

from sqlalchemy.exc import (
    DataError,
    IntegrityError,
    MultipleResultsFound,
    NoResultFound,
    OperationalError,
    ProgrammingError,
    SQLAlchemyError,
)

from api.v1.utils.logger import get_logger

logger = get_logger("exception_handler")


def _request_meta(request: Request) -> dict:
    return {
        "request_id": getattr(request.state, "request_id", None),
        "path": request.url.path,
        "method": request.method,
    }


def _error_response(status_code: int, message: str, **extra) -> JSONResponse:
    body = {"success": False, "status_code": status_code, "message": message}
    body.update(extra)
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append(
            {
                "field": field or "body",
                "message": error["msg"],
                "type": error["type"],
            }
        )

    logger.warning(
        "Validation error",
        extra={**_request_meta(request), "errors": errors},
    )

    return _error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Validation error",
        errors=errors,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    logger.warning(
        "HTTP exception",
        extra={
            **_request_meta(request),
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
    )
    return _error_response(exc.status_code, exc.detail)


async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    _status_messages = {
        400: "Bad request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Resource not found",
        405: "Method not allowed",
        408: "Request timeout",
        409: "Conflict",
        410: "Resource gone",
        429: "Too many requests",
        500: "Internal server error",
        502: "Bad gateway",
        503: "Service unavailable",
        504: "Gateway timeout",
    }
    message = exc.detail or _status_messages.get(exc.status_code, "An error occurred")

    log_level = "warning" if exc.status_code < 500 else "error"
    getattr(logger, log_level)(
        "Starlette HTTP exception",
        extra={
            **_request_meta(request),
            "status_code": exc.status_code,
            "response_message": message,
        },
    )
    return _error_response(exc.status_code, message)


async def sqlalchemy_integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    orig_str = str(getattr(exc, "orig", "") or "").lower()

    if "unique" in orig_str or "duplicate" in orig_str:
        message = "A record with this value already exists"
        status_code = status.HTTP_409_CONFLICT
    elif "foreign key" in orig_str or "foreignkey" in orig_str:
        message = "Referenced record does not exist"
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif "not null" in orig_str or "notnull" in orig_str:
        message = "A required field is missing"
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        message = "Database constraint violation"
        status_code = status.HTTP_400_BAD_REQUEST

    logger.warning(
        "SQLAlchemy integrity error",
        extra={**_request_meta(request), "error_message": str(exc.orig)},
    )
    return _error_response(status_code, message)


async def sqlalchemy_operational_error_handler(
    request: Request, exc: OperationalError
) -> JSONResponse:
    logger.error(
        "SQLAlchemy operational error",
        extra={
            **_request_meta(request),
            "error_message": str(exc.orig),
        },
        exc_info=True,
    )
    return _error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Database connection unavailable. Please try again later.",
    )


async def sqlalchemy_data_error_handler(
    request: Request, exc: DataError
) -> JSONResponse:
    logger.warning(
        "SQLAlchemy data error",
        extra={**_request_meta(request), "error_message": str(exc.orig)},
    )
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Invalid data for the requested operation.",
    )


async def sqlalchemy_programming_error_handler(
    request: Request, exc: ProgrammingError
) -> JSONResponse:
    logger.error(
        "SQLAlchemy programming error",
        extra={**_request_meta(request), "error_message": str(exc.orig)},
        exc_info=True,
    )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "A database configuration error occurred. Please contact support.",
    )


async def sqlalchemy_no_result_found_handler(
    request: Request, exc: NoResultFound
) -> JSONResponse:
    logger.warning(
        "No result found",
        extra={**_request_meta(request), "error_message": str(exc)},
    )
    return _error_response(status.HTTP_404_NOT_FOUND, "The requested record was not found.")


async def sqlalchemy_multiple_results_found_handler(
    request: Request, exc: MultipleResultsFound
) -> JSONResponse:
    logger.error(
        "Multiple results found",
        extra={**_request_meta(request), "error_message": str(exc)},
        exc_info=True,
    )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "An unexpected data integrity error occurred.",
    )


async def sqlalchemy_generic_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.error(
        "Unhandled SQLAlchemy error",
        extra={
            **_request_meta(request),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        },
        exc_info=True,
    )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "An unexpected database error occurred. Please try again later.",
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unexpected error",
        extra={
            **_request_meta(request),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        },
        exc_info=True,
    )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "An unexpected error occurred. Please try again later.",
    )
