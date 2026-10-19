from inspect import iscoroutinefunction
import traceback
from typing import Callable

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .exceptions import (
    ApplicationException,
    AuthenticationTimeoutException,
    BadRequestException,
    ForbiddenException,
    MethodNotAllowException,
    NotFoundException,
    RequestValidationError,
    UnauthorizedException,
    UnsupportedMediaTypeException,
)
from .messages import (
    get_message,
    resolve_locale,
    translate_validation_msg,
)
from ..responses import common_response, build_response


# Starlette 路由层抛出的原生 需映射到 PyreStarlette ApplicationException，
HTTP_STATUS_APPLICATION_EXCEPTION: dict[int, type[ApplicationException]] = {
    400: BadRequestException,
    401: UnauthorizedException,
    403: ForbiddenException,
    404: NotFoundException,
    405: MethodNotAllowException,
    415: UnsupportedMediaTypeException,
    419: AuthenticationTimeoutException,
}


def _merge_response_headers(response: Response, headers: dict[str, str] | None) -> Response:
    if not headers:
        return response
    existing = {k.lower() for k in response.headers.keys()}
    for key, value in headers.items():
        if key.lower() not in existing:
            response.headers[key] = value
    return response


def init_app_errorhandler(
    app: Starlette,
) -> None:
    """
    Register global Exception handler, and automatically wrap the return value.
    """
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(ApplicationException, application_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, exception_handler)


async def exception_handler(request: Request, exc: Exception) -> Response:
    """Unhandled exception fallback."""
    locale = resolve_locale(request)
    response = common_response(code=500, msg=get_message("Internal Server Error", locale))
    return JSONResponse(
        status_code=500,
        content=response,
    )


async def application_exception_handler(request: Request, exc: ApplicationException) -> Response:
    """Application Exception Handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
        headers=exc.headers,
    )


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    """HTTP Exception Handler"""
    headers = getattr(exc, "headers", None)
    status_code = getattr(exc, "status_code", 500)

    locale = resolve_locale(request)
    default_detail = get_message("Internal Server Error", locale)
    detail = getattr(exc, "detail", default_detail) or default_detail

    # Starlette 原生 HTTPException → 转发到用户注册的 ApplicationException handler
    if isinstance(exc, HTTPException):
        app_exc_class = HTTP_STATUS_APPLICATION_EXCEPTION.get(status_code)
        if app_exc_class is not None:
            custom_handler = request.app.exception_handlers.get(app_exc_class)
            if custom_handler is not None:
                response = await custom_handler(request, app_exc_class())
                return _merge_response_headers(response, headers)

    if type(exc) is HTTPException:
        locale = resolve_locale(request)
        message = get_message(detail, locale)
    else:
        message = detail
    return JSONResponse(
        status_code=status_code,
        content=common_response(code=status_code, msg=message),
        headers=headers,
    )


async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
    status_code: int = 400,
    print_traceback: bool = False,
) -> Response:
    """Request Validation Error Handler"""
    return await validation_exception_handler(request, exc, status_code, print_traceback)


async def validation_exception_handler(
    request: Request,
    exc: ValidationError,
    status_code: int = 500,
    print_traceback: bool = True,
) -> Response:
    """Validation Error Handler"""
    locale = resolve_locale(request)
    errors = exc.errors()
    loc = errors[0]['loc']
    if len(loc) >= 3:
        loc_list = [str(i) if i != 0 else '中的' for i in loc]
        key = ' '.join(loc_list)
    elif len(loc) == 2:
        key = f"'{loc[0]}' 中的 '{loc[1]}'"
    else:
        key = loc[0] if len(loc) == 1 else getattr(errors[0], 'key', getattr(exc, 'key', 'unknown'))
    error = errors[0]
    msg = translate_validation_msg(error.get('msg', ''), error.get('type', ''), locale)

    message = f"{get_message('Request Validation Error', locale)}, {get_message('Field', locale)} '{key}' {msg}"
    if print_traceback:
        traceback.print_exc()
    return JSONResponse(
        status_code=status_code,
        content=common_response(code=status_code, msg=message),
    )


def wrap_exception_handler(handler: Callable) -> Callable:
    """Wrap Exception Handler"""

    if iscoroutinefunction(handler):
        async def async_wrapper(request: Request, exc: Exception) -> Response:
            result = await handler(request, exc)
            if isinstance(result, Response):
                return result
            return build_response(result, status_code=getattr(exc, "status_code", 200))
        return async_wrapper

    async def sync_wrapper(request: Request, exc: Exception) -> Response:
        result = handler(request, exc)
        if isinstance(result, Response):
            return result
        return build_response(result, status_code=getattr(exc, "status_code", 200))

    return sync_wrapper
