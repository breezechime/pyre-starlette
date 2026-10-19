import hmac
import hashlib
import warnings
import base64
from functools import wraps
from random import SystemRandom, Random
from typing import Optional, Callable, Union, Any, Generic, Literal, Tuple

from starlette._utils import is_async_callable
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from ..constants import _T
from ..requests import get_request
from ..exceptions import (
    UnauthorizedException,
    ForbiddenException,
    AuthenticationTimeoutException,
)


class HTTPAuth(Generic[_T]):
    """
    HTTP认证基类
    HTTP authentication base class
    """

    def __init__(
        self,
        scheme: Optional[str] = None,
        realm: Optional[str] = None,
        header_key: Optional[str] = None,
    ):
        self.scheme = scheme
        self.realm = realm or "Authentication Required"
        self.header_key = header_key or "Authorization"

    def authenticate_headers(self):
        """
        认证请求头
        Authentication request headers
        """
        return {'WWW-Authenticate': '{0} realm="{1}"'.format(self.scheme, self.realm)}

    def authenticate(self, request: Request, *args, **kwargs) -> Optional[Union[_T, bool, Any]]:
        """
        校验登录认证
        Validate login authentication
        """
        warnings.warn("authenticate method is not implemented", UserWarning)
        return False

    def authorize(
        self,
        request: Request,
        user: _T,
        roles: Optional[Union[str, list[str], Any]] = None,
        permissions: Optional[Union[str, list[str], Any]] = None,
        *args,
        **kwargs: Any
    ):
        """
        校验操作授权
        Validate operation authorization
        """
        if not roles and not permissions:
            return True
        warnings.warn("authorize method is not implemented", UserWarning)
        if roles and not self.has_role(*roles):
            return False
        if permissions and not self.has_permission(*permissions):
            return False
        return True

    def login_required(
        self,
        func: Optional[Callable] = None,
        roles: Optional[Union[str, list[str], Any]] = None,
        permissions: Optional[Union[str, list[str], Any]] = None,
        optional: Optional[bool] = None,
        **kw: Any
    ):
        """
        要求登录认证装饰器
        Require login authentication for decorator
        """
        def precheck() -> Optional[Union[_T, bool, Any]]:
            try:
                request = get_request()
                cache_key = f"_pyre_auth_prechecked_{id(precheck)}"
                cached_user = getattr(request.state, cache_key, None)
                if cached_user is not None:
                    self.set_current_user(cached_user)
                    return cached_user

                user = self.authenticate(request, **kw)

                status = None
                if user in (False, None):
                    status = 401
                elif self.is_superuser(user):
                    status = None
                elif not self.authorize(request, user, roles=roles, permissions=permissions, **kw):
                    status = 403
                if not optional and status:
                    return self.auth_error_callback(status)
            except Exception as e:
                return self.auth_error_callback(exc=e)

            self.set_current_user(user)
            setattr(request.state, cache_key, user)
            return user

        def login_required_internal(endpoint):
            if is_async_callable(endpoint):
                @wraps(endpoint)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    precheck()
                    return await endpoint(*args, **kwargs)
                async_wrapper.__pyre_auth_required__ = True
                async_wrapper.__pyre_auth_scheme__ = self.scheme
                async_wrapper.__pyre_auth_name__ = getattr(self, 'security_name', 'BearerAuth')
                async_wrapper.__pyre_auth_precheck__ = precheck
                return async_wrapper

            @wraps(endpoint)
            async def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                def invoke() -> Any:
                    precheck()
                    return endpoint(*args, **kwargs)
                return await run_in_threadpool(invoke)
            sync_wrapper.__pyre_auth_required__ = True
            sync_wrapper.__pyre_auth_scheme__ = self.scheme
            sync_wrapper.__pyre_auth_name__ = getattr(self, 'security_name', 'BearerAuth')
            sync_wrapper.__pyre_auth_precheck__ = precheck
            return sync_wrapper

        if func:
            return login_required_internal(func)
        return login_required_internal

    def permission_required(
        self,
        func: Optional[Callable] = None,
        permissions: Optional[Union[str, list[str], Any]] = None,
        **kwargs: Any
    ):
        """
        要求登录认证后验证权限装饰器
        Require login authentication and verification of permission decorator
        """
        return self.login_required(
            func,
            permissions=permissions,
            **kwargs
        )

    def role_required(
        self,
        func: Optional[Callable] = None,
        roles: Optional[Union[str, list[str], Any]] = None,
        **kwargs: Any
    ):
        """
        要求登录认证后验证角色装饰器
        Require verification of role decorator after login authentication
        """
        return self.login_required(
            func,
            roles=roles,
            **kwargs
        )

    def auth_error_callback(self, status: Optional[int] = None, exc: Optional[Exception] = None):
        """
        认证异常回调
        Authentication exception callback
        """
        if exc:
            raise exc

        if status == 419:
            raise AuthenticationTimeoutException(headers=self.authenticate_headers())
        elif status == 403:
            raise ForbiddenException(headers=self.authenticate_headers())

        raise UnauthorizedException(headers=self.authenticate_headers())

    def has_role(self, *role, method: Literal["and", "or"] = 'and') -> bool:
        """
        判断用户是否包含指定角色
        Judge if the user contains the specified role
        """
        raise NotImplementedError("has_role method is not implemented")

    def has_permission(self, *permission, method: Literal["and", "or"] = 'and') -> bool:
        """
        判断用户是否包含指定权限
        Judge if the user contains the specified permission
        """
        raise NotImplementedError("has_permission method is not implemented")

    def check_role(self, *role, method: Literal["and", "or"] = 'and') -> bool:
        """
        检查用户是否包含指定角色
        Check if the user contains the specified role
        """
        if not self.has_role(*role, method=method):
            return self.auth_error_callback(status=403)
        return True

    def check_permission(self, *permission, method: Literal["and", "or"] = 'and') -> bool:
        """
        检查用户是否包含指定权限
        Check if the user contains the specified permission
        """
        if not self.has_permission(*permission, method=method):
            return self.auth_error_callback(status=403)
        return True

    def current_user(self, raise_error: bool = False) -> Optional[_T]:
        """
        获取当前用户
        Get the current user
        """
        request = get_request()
        try:
            user = request.state['user']
        except KeyError:
            user = None
        if raise_error and user is None:
            raise self.auth_error_callback(status=401)
        return user

    def set_current_user(self, user: _T) -> None:
        """
        设置当前用户
        Set the current user
        """
        request = get_request()
        request.state['user'] = user

    def current_user_id(self):
        """
        获取当前用户ID
        Get the ID of the current user
        """
        raise NotImplementedError("get_current_user_id method is not implemented")

    def is_superuser(self, user: _T) -> bool:
        """
        判断是否为超级管理员账号
        Judge if the user is a superuser account
        """
        return False


class HTTPBasicAuth(HTTPAuth[Generic[_T]]):
    """
    HTTP Basic认证
    HTTP Basic authentication
    """

    def __init__(
        self,
        scheme: Optional[str] = None,
        realm: Optional[str] = None,
        header_key: Optional[str] = None,
        verify_password_callback: Optional[Callable] = None,
    ):
        self._verify_password_callback = verify_password_callback
        super().__init__(scheme or 'Basic', realm, header_key)

    def verify_password(self, func):
        """
        设置校验密码的回调函数
        Set the callback function to validate the password
        """
        self._verify_password_callback = func
        return func

    def verify_password_callback(self, username: str, password: str):
        """
        校验密码
        Validate password
        """
        if self._verify_password_callback:
            return self._verify_password_callback(username, password)
        raise NotImplementedError("verify_password method is not implemented")

    def authenticate(self, request: Request, *args, **kwargs) -> Optional[Union[_T, bool, Any]]:
        """
        校验登录认证
        Validate login authentication
        """
        authorization = request.headers.get(self.header_key or 'Authorization')
        if not authorization:
            return None
        try:
            authorization = authorization.strip().encode('utf-8')
            _, credentials = authorization.split(b' ', 1)
            encoded_username, encoded_password = base64.b64decode(credentials).split(b':', 1)
        except (ValueError, TypeError):
            return None
        try:
            username = encoded_username.decode('utf-8')
            password = encoded_password.decode('utf-8')
        except UnicodeDecodeError:
            # try to decode again with latin-1, which should always work
            username = encoded_username.decode('latin1')
            password = encoded_password.decode('latin1')
        return self.verify_password_callback(username, password)


class HTTPDigestAuth(HTTPAuth[_T]):
    """
    HTTP Digest认证
    HTTP Digest authentication
    """

    def __init__(
        self,
        scheme: Optional[str] = None,
        realm: Optional[str] = None,
        header_key: Optional[str] = None,
        use_ha1_pw=False,
        qop='auth',
        algorithm='MD5',
        get_user_and_password_callback: Optional[Callable] = None,
        generate_nonce_callback: Optional[Callable] = None,
        verify_nonce_callback: Optional[Callable] = None,
        generate_opaque_callback: Optional[Callable] = None,
        verify_opaque_callback: Optional[Callable] = None
    ):
        self.use_ha1_pw = use_ha1_pw
        if isinstance(qop, str):
            self.qop = [v.strip() for v in qop.split(',')]
        else:
            self.qop = qop
        if algorithm.lower() == 'md5':
            self.algorithm = 'MD5'
        elif algorithm.lower() == 'md5-sess':
            self.algorithm = 'MD5-Sess'
        else:
            raise ValueError(f'Algorithm {algorithm} is not supported')

        self.random = SystemRandom()
        try:
            self.random.random()
        except NotImplementedError:  # pragma: no cover
            self.random = Random()

        self._get_user_and_password_callback = get_user_and_password_callback
        self._generate_nonce_callback = generate_nonce_callback
        self._verify_nonce_callback = verify_nonce_callback
        self._generate_opaque_callback = generate_opaque_callback
        self._verify_opaque_callback = verify_opaque_callback
        super().__init__(scheme or 'Digest', realm, header_key)

    def get_user_and_password(self, func):
        """
        设置获取用户名和密码的回调函数
        Set the callback function to get user and password
        """
        self._get_user_and_password_callback = func
        return func

    def get_user_and_password_callback(self, username: str) -> Optional[Union[str, Tuple[_T, str]]]:
        """
        获取用户名和密码
        Get username and password
        """
        if self._get_user_and_password_callback:
            return self._get_user_and_password_callback(username)
        raise NotImplementedError('get_user_and_password_callback is not implemented')

    def authenticate_headers(self):
        """
        生成认证头
        Generate authentication headers
        """
        request = get_request()
        nonce = self.generate_nonce(request)
        opaque = self.generate_opaque(request)
        request.session['auth_nonce'] = nonce
        request.session['auth_opaque'] = opaque

        if self.qop:
            value = ('{0} realm="{1}",nonce="{2}",opaque="{3}",algorithm="{4}",qop="{5}"').format(
                self.scheme,
                self.realm,
                nonce,
                opaque,
                self.algorithm,
                ','.join(self.qop)
            )
        else:
            value = '{0} realm="{1}",nonce="{2}",opaque="{3}"'.format(
                self.scheme,
                self.realm,
                nonce,
                opaque
            )

        return {'WWW-Authenticate': value}

    def _generate_random(self):
        """
        生成随机数
        Generate random number
        """
        return hashlib.md5(str(self.random.random()).encode('utf-8')).hexdigest()

    def authenticate(self, request: Request, *args, **kwargs) -> Optional[Union[_T, bool, Any]]:
        """
        校验登录认证
        Validate login authentication
        """
        authorization = request.headers.get(self.header_key)
        if not authorization:
            return None
        try:
            _, credentials = authorization.split(' ', 1)
            params = {}
            for param in credentials.split(','):
                key, value = param.split('=')
                params[key.strip()] = value.strip().strip('"')
        except (ValueError, TypeError):
            return None

        if not params.get('username') or not params.get('realm') or \
                not params.get('nonce') or not params.get('response') or not params.get('uri'):
            return False
        if not self.verify_nonce(params.get('nonce'), request) or \
                not self.verify_opaque(params.get('opaque'), request):
            return False
        if params.get('qop') and params.get('qop') not in self.qop:
            return False
        user_and_password = self.get_user_and_password_callback(params.get('username'))
        if isinstance(user_and_password, tuple):
            user, password = user_and_password
        else:
            user = password = user_and_password
        if not password:
            return False
        if self.use_ha1_pw:
            ha1 = password
        else:
            a1 = params.get('username') + ':' + params.get('realm') + ':' + password
            ha1 = hashlib.md5(a1.encode('utf-8')).hexdigest()
        if self.algorithm == 'MD5-Sess':
            ha1 = hashlib.md5((ha1 + params.get('nonce') + params.get('cnonce')).encode('utf-8')).hexdigest()
        a2 = request.method + ':' + params.get('uri')
        ha2 = hashlib.md5(a2.encode('utf-8')).hexdigest()
        if params.get('qop') == 'auth':
            a3 = ha1 + ":" + params.get('nonce') + ":" + params.get('nc') + ":" + \
                params.get('cnonce') + ":auth:" + ha2
        else:
            a3 = ha1 + ":" + params.get('nonce') + ":" + ha2
        response = hashlib.md5(a3.encode('utf-8')).hexdigest()
        if hmac.compare_digest(response, params.get('response')):
            return user
        return False

    def generate_nonce(self, request: Request):
        """
        生成nonce
        Generate nonce
        """
        if self._generate_nonce_callback:
            return self._generate_nonce_callback(request)
        return self._generate_random()

    def generate_opaque(self, request: Request):
        """
        生成opaque
        Generate opaque
        """
        if self._generate_opaque_callback:
            return self._generate_opaque_callback(request)
        return self._generate_random()

    def verify_nonce(self, nonce: str, request: Request):
        """
        校验nonce
        Validate nonce
        """
        if self._verify_nonce_callback:
            return self._verify_nonce_callback(nonce, request)
        session_nonce = request.session.get('auth_nonce')
        if not session_nonce:
            return False
        return hmac.compare_digest(nonce, session_nonce)

    def verify_opaque(self, opaque: str, request: Request):
        """
        校验opaque
        Validate opaque
        """
        if self._verify_opaque_callback:
            return self._verify_opaque_callback(opaque, request)
        session_opaque = request.session.get('auth_opaque')
        if not session_opaque:
            return False
        return hmac.compare_digest(opaque, session_opaque)


class HTTPTokenAuth(HTTPAuth[_T]):
    """
    基于token的HTTP认证
    HTTP authentication based on token
    """

    def __init__(
        self,
        scheme: Optional[str] = None,
        realm: Optional[str] = None,
        header_key: Optional[str] = None,
        verify_token_callback: Optional[Callable] = None,
        security_name: Optional[str] = None,
    ):
        self._verify_token_callback = verify_token_callback
        self.security_name = security_name or "BearerAuth"
        super().__init__(scheme or 'Bearer', realm, header_key)

    def verify_token(self, func):
        """
        设置token校验函数
        Set token verification function
        """
        self._verify_token_callback = func
        return self

    def verify_token_callback(self, token: str):
        """
        校验token
        Validate token
        """
        if self._verify_token_callback:
            return self._verify_token_callback(token)
        raise NotImplementedError("verify_token_callback is not implemented")

    def authenticate(self, request: Request, *args, **kwargs) -> Optional[Union[_T, bool, Any]]:
        """
        校验登录认证
        Validate login authentication
        """
        authorization = request.headers.get(self.header_key)
        if not authorization:
            return None
        try:
            if ' ' in authorization:
                _, token = authorization.split(' ', 1)
            else:
                token = authorization
        except (ValueError, TypeError):
            return None
        return self.verify_token_callback(token)

    def get_token(self) -> Optional[str]:
        request = get_request()
        authorization = request.headers.get(self.header_key)
        if not authorization:
            return None
        if ' ' in authorization:
            _, token = authorization.split(' ', 1)
            return token
        return authorization
