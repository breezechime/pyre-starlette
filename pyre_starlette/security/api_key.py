from typing import Optional, Callable, Literal, Union, Any

from starlette.requests import Request
from .http import HTTPAuth
from ..constants import _T


class HTTPApiKeyAuth(HTTPAuth[_T]):
    """
    HTTP ApiKey 认证
    """

    def __init__(
        self,
        scheme: Optional[str] = None,
        realm: Optional[str] = None,
        api_key_name: str = 'X-API-Key',
        verify_api_key_callback: Optional[Callable] = None,
        location: Literal["header", "query", "cookie"] = "header",
    ):
        self.api_key_name = api_key_name
        self.location = location
        self._verify_api_key_callback = verify_api_key_callback
        super().__init__(scheme or 'Bearer', realm, api_key_name)

    def verify_api_key(self, func):
        """
        设置 ApiKey 验证回调
        Set ApiKey verify callback
        """
        self._verify_api_key_callback = func

    def verify_api_key_callback(self, api_key: str):
        """
        ApiKey 验证回调
        ApiKey verify callback
        """
        if self._verify_api_key_callback:
            return self._verify_api_key_callback(api_key)
        raise NotImplementedError("verify_api_key_callback is not implemented")

    def authenticate(self, request: Request, *args, **kwargs) -> Optional[Union[_T, bool, Any]]:
        """
        校验登录认证
        Validate login authentication
        """
        if self.location == "header":
            authorization = request.headers.get(self.api_key_name)
        elif self.location == "query":
            authorization = request.query_params.get(self.api_key_name)
        elif self.location == "cookie":
            authorization = request.cookies.get(self.api_key_name)
        else:
            raise ValueError(f"Invalid location: {self.location}")
        if not authorization:
            return None
        try:
            if ' ' in authorization:
                _, api_key = authorization.split(' ', 1)
            else:
                api_key = authorization
        except (ValueError, TypeError):
            return None
        return self.verify_api_key_callback(api_key)
