from starlette.middleware import Middleware as Middleware  # noqa: F401
from starlette.middleware.cors import CORSMiddleware as CORSMiddleware  # noqa: F401
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from pyre_starlette.requests import bind_request, reset_request


class RequestContextMiddleware(BaseHTTPMiddleware):
    """请求上下文绑定中间件"""

    async def dispatch(self, request: Request, call_next):
        token = bind_request(request)
        try:
            return await call_next(request)
        finally:
            reset_request(token)