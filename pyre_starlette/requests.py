from contextvars import ContextVar, Token
from functools import wraps
from typing import Any, Callable, ClassVar, Optional

from starlette._utils import is_async_callable
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection as HTTPConnection  # noqa: F401
from starlette.requests import Request as Request  # noqa: F401

request_ctx: ClassVar[ContextVar[Optional[Request]]] = ContextVar(
    "pyre_starlette_request_ctx",
    default=None,
)


def bind_request(request: Request) -> Token:
    """Bind the current request to context. / 将当前请求绑定到上下文。"""
    return request_ctx.set(request)


def reset_request(token: Token) -> None:
    """Reset request context to the previous value. / 恢复上一层的请求上下文。"""
    request_ctx.reset(token)


def get_request() -> Request:
    """Return the active request from context. / 从上下文获取当前请求。"""
    request = request_ctx.get()
    if request is None:
        raise RuntimeError("No active Request in context")
    return request


def try_get_request() -> Optional[Request]:
    """Return the active request or None. / 获取当前请求，不存在则返回 None。"""
    return request_ctx.get()


def with_request_context(
    handler: Callable[[Request], Any],
) -> Callable[[Request], Any]:
    if is_async_callable(handler):

        @wraps(handler)
        async def async_wrapper(request: Request) -> Any:
            token = bind_request(request)
            try:
                return await handler(request)
            finally:
                reset_request(token)

        return async_wrapper

    @wraps(handler)
    async def sync_wrapper(request: Request) -> Any:
        token = bind_request(request)
        try:
            return await run_in_threadpool(handler, request)
        finally:
            reset_request(token)

    return sync_wrapper
