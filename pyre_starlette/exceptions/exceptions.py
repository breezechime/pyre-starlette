from typing import Any, Mapping, Optional

from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..responses import common_response


class HTTPException(StarletteHTTPException):

    def __init__(
        self,
        status_code: int,
        detail: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(status_code, detail, headers)


class RequestValidationError(ValidationError):
    """Request validation error"""


class ApplicationException(HTTPException):
    """Application exception"""

    MESSAGE_KEY: str = "Internal Server Error"

    def __init__(
        self,
        code: int = 500,
        msg: Optional[str] = None,
        status_code: int = 500,
        headers: Mapping[str, str] | None = None,
        skip_error_handler: bool = False,
        **kwargs
    ) -> None:
        self.code = code
        self.message_key = self.MESSAGE_KEY
        self.msg = msg
        self.status_code = status_code
        self.skip_error_handler = skip_error_handler
        self.headers = headers
        self.kwargs = kwargs

        response = common_response(code=code, msg=msg or self.MESSAGE_KEY, **kwargs)
        super().__init__(status_code=status_code, detail=response, headers=headers)


class BadRequestException(ApplicationException):
    MESSAGE_KEY = "Request Parameter Error"

    def __init__(
        self,
        code: int = 400,
        msg: Optional[str] = None,
        status_code: int = 400,
        skip_error_handler: bool = True,
        **kwargs
    ) -> None:
        super().__init__(
            code=code, msg=msg, status_code=status_code, skip_error_handler=skip_error_handler, **kwargs
        )


class UnauthorizedException(ApplicationException):
    MESSAGE_KEY = "Unauthorized"

    def __init__(
        self,
        code: int = 401,
        msg: Optional[str] = None,
        status_code: int = 401,
        skip_error_handler: bool = True,
        **kwargs
    ) -> None:
        super().__init__(
            code=code,
            msg=msg,
            status_code=status_code,
            skip_error_handler=skip_error_handler,
            **kwargs
        )


class ForbiddenException(ApplicationException):
    MESSAGE_KEY = "Forbidden"

    def __init__(
        self,
        code: int = 403,
        msg: Optional[str] = None,
        status_code: int = 403,
        skip_error_handler: bool = True,
        **kwargs
    ) -> None:
        super().__init__(
            code=code,
            msg=msg,
            status_code=status_code,
            skip_error_handler=skip_error_handler,
            **kwargs
        )


class NotFoundException(ApplicationException):
    MESSAGE_KEY = "The requested URL was not found on the server"

    def __init__(
        self,
        code: int = 404,
        msg: Optional[str] = None,
        status_code: int = 404,
        skip_error_handler: bool = True,
        **kwargs
    ) -> None:
        super().__init__(
            code=code,
            msg=msg,
            status_code=status_code,
            skip_error_handler=skip_error_handler,
            **kwargs
        )


class NotFoundDataException(ApplicationException):
    MESSAGE_KEY = "Not Found Data"

    def __init__(
        self,
        code: int = 404,
        msg: Optional[str] = None,
        status_code: int = 404,
        skip_error_handler: bool = False,
        **kwargs
    ) -> None:
        super().__init__(
            code=code,
            msg=msg,
            status_code=status_code,
            skip_error_handler=skip_error_handler,
            **kwargs
        )


class MethodNotAllowException(ApplicationException):
    MESSAGE_KEY = "The method is not allowed for the requested URL"

    def __init__(
        self,
        code: int = 405,
        msg: Optional[str] = None,
        status_code: int = 405,
        skip_error_handler: bool = True,
        **kwargs
    ):
        super().__init__(
            code=code,
            msg=msg,
            status_code=status_code,
            skip_error_handler=skip_error_handler,
            **kwargs
        )


class UnsupportedMediaTypeException(ApplicationException):
    MESSAGE_KEY = "The server does not support the media type transmitted in the request"

    def __init__(
        self,
        code: int = 415,
        msg: Optional[str] = None,
        status_code: int = 415,
        skip_error_handler: bool = True,
        **kwargs
    ):
        super().__init__(
            code=code,
            msg=msg,
            status_code=status_code,
            skip_error_handler=skip_error_handler,
            **kwargs
        )


class AuthenticationTimeoutException(ApplicationException):
    MESSAGE_KEY = "Authentication Timeout"

    def __init__(
        self,
        code: int = 419,
        msg: Optional[str] = None,
        status_code: int = 419,
        skip_error_handler: bool = True,
        **kwargs
    ) -> None:
        super().__init__(
            code=code,
            msg=msg,
            status_code=status_code,
            skip_error_handler=skip_error_handler,
            **kwargs
        )
