"""Every failed request returns an ErrorBody with a code from 03-contract.md section 3."""

import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from twyf.contract.models import ErrorBody, ErrorInfo, dump
from twyf.services.errors import HTTP_STATUS, ServiceError

log = logging.getLogger(__name__)


def error_response(code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body = ErrorBody(error=ErrorInfo(code=code, message=message, details=details))
    return JSONResponse(dump(body), status_code=HTTP_STATUS[code])


def from_service_error(error: ServiceError) -> JSONResponse:
    return error_response(error.code, error.message, error.details)


def from_validation_error(error: ValidationError) -> JSONResponse:
    return error_response(
        "validation", "The input does not match the operation", {"errors": json.loads(error.json(include_url=False))}
    )


def internal(error: BaseException) -> JSONResponse:
    log.error("internal error", exc_info=error)
    return error_response("internal", "Something went wrong. The details are in the server log.")


def install(app: FastAPI) -> None:
    async def service_error(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, ServiceError)
        return from_service_error(error)

    async def request_validation(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, RequestValidationError)
        errors: list[Any] = json.loads(json.dumps(list(error.errors()), default=str))
        return error_response("validation", "The input does not match the operation", {"errors": errors})

    async def http_error(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, HTTPException)
        if error.status_code == 404:
            return error_response("not_found", "No such route")
        if 400 <= error.status_code < 500:
            return error_response("validation", str(error.detail))
        return error_response("internal", "Something went wrong.")

    app.add_exception_handler(ServiceError, service_error)
    app.add_exception_handler(RequestValidationError, request_validation)
    app.add_exception_handler(HTTPException, http_error)
