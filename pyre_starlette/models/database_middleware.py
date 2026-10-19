from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Awaitable, Callable

from sqlalchemy_db import TransactionManager, AsyncTransactionManager, Propagation


class DatabaseMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, db_instance=None, async_mode='auto'):
        super().__init__(app)
        self.db_instance = db_instance
        self.async_mode = async_mode

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if self.db_instance is None:
            raise RuntimeError('DatabaseMiddleware 需要传入 db_instance。')

        autocommit = self.db_instance.autocommit
        alias = self.db_instance.alias

        is_async = self._is_async_mode()

        if is_async:
            async with AsyncTransactionManager(
                alias=alias, propagation=Propagation.NEW, autocommit=autocommit
            ):
                return await call_next(request)
        else:
            with TransactionManager(
                alias=alias, propagation=Propagation.NEW, autocommit=autocommit
            ):
                return await call_next(request)

    def _is_async_mode(self) -> bool:
        if self.async_mode == 'sync':
            return False
        if self.async_mode == 'async':
            return True
        
        if hasattr(self.db_instance, 'async_mode'):
            return self.db_instance.async_mode == 'async'
        
        if self.db_instance.engines:
            engine = self.db_instance.engines.get(None)
            from sqlalchemy.ext.asyncio import AsyncEngine
            return isinstance(engine, AsyncEngine)
        
        return False