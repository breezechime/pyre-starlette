import asyncio
import logging
import typing
import platform
from starlette import __version__ as starlette_version

from pathlib import Path
from typing import Awaitable, Callable, Optional, List, Any, Union

from pyre_config import ConfigLoader, Environment
from pyre_injector import DependencyContainer
from sqlalchemy_db import SQLAlchemyDB


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware import _MiddlewareFactory, P
from starlette.applications import Starlette, AppType
from starlette.datastructures import State
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response, HTMLResponse
from starlette.routing import BaseRoute
from starlette.types import ASGIApp, ExceptionHandler, Lifespan


try:
    from redis import Redis
except ImportError:
    redis = None
    Redis = None

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from .middleware import RequestContextMiddleware
from .constants import ART_TEXT
from .logger import PyreLogging
from .routing import Router, Route
from .openapi import PyreStarletteOpenapi
from .config import AppConfig, OpenapiConfig, PyreConfig
from .exceptions.exception_handlers import init_app_errorhandler, wrap_exception_handler
from .models.database_middleware import DatabaseMiddleware


class PyreStarlette(Starlette):
    """应用的艺术字文本"""
    art_text: str = ART_TEXT

    """SQLAlchemyDB 数据库组件"""
    sqlalchemy_db = SQLAlchemyDB

    """依赖注入"""
    dependency_container_class = DependencyContainer

    environment_class = Environment

    app_config_class = AppConfig

    logging_class = PyreLogging

    def _add_request_context_middleware(self):
        """添加请求上下文绑定中间件（必须是第一个中间件）"""
        self.user_middleware.insert(0, Middleware(RequestContextMiddleware))

    def __init__(
        self,
        debug: bool = False,
        routes: typing.Sequence[BaseRoute] | None = None,
        middleware: typing.Sequence[Middleware] | None = None,
        redirect_slashes: bool = True,
        exception_handlers: Optional[typing.Mapping[Any, ExceptionHandler]] = None,
        lifespan: typing.Optional[Lifespan["AppType"]] = None,
        app_config: Optional[Union[AppConfig, dict]] = None,
        openapi_config: Optional[OpenapiConfig] = None,
        config_loader: Optional[ConfigLoader] = None,
        init_app: bool = True,
        include_openapi: bool = True,
        route_class: type[Route] = Route,
        notice: bool = True,
    ):
        # 先让基类初始化默认属性；Starlette 不同版本会新增属性（如 1.6 的 max_body_size），
        # 这里不调用基类就会在升级后丢失它们。下面再覆盖本框架需要自定义的部分。
        super().__init__()

        # overwrite starlette
        self.debug = debug
        self.state = State()
        self.router = Router(
            routes=routes,
            redirect_slashes=redirect_slashes,
            lifespan=lifespan,
            include_openapi=include_openapi,
            route_class=route_class
        )
        self.exception_handlers: dict[
            Any, Callable[[Request, Any], Response | Awaitable[Response]]
        ] = {} if exception_handlers is None else dict(exception_handlers)
        self.user_middleware: list[Middleware] = [] if middleware is None else list(middleware)
        self.middleware_stack: Optional[ASGIApp] = None

        self._add_request_context_middleware()

        # global exception handler
        init_app_errorhandler(self)

        # config
        self._config_dict: typing.Dict[str, typing.Any] = {}
        # configuration
        self.config_loader = config_loader or ConfigLoader()

        if isinstance(app_config, dict):
            self._config_dict = app_config
            self.app_config: AppConfig = self.app_config_class(**self._config_dict)
        elif isinstance(app_config, AppConfig):
            self._config_dict = app_config.model_dump(mode='json', exclude_none=True, exclude_unset=True)
            self.app_config: AppConfig = app_config
        else:
            self.app_config: AppConfig = self.app_config_class(**self._config_dict)

        override: Optional[PyreConfig] = None
        if openapi_config is not None and isinstance(openapi_config, dict):
            override = PyreConfig(openapi=openapi_config)
        elif openapi_config is not None and isinstance(openapi_config, OpenapiConfig):
            override = PyreConfig(openapi=openapi_config.model_dump(mode='json', exclude_none=True, exclude_unset=True))
        if override is not None:
            self._config_dict = self.config_loader.safe_merge_config_dict(
                {"pyre": override.model_dump(mode='json', exclude_none=True, exclude_unset=True)},
                self._config_dict,
            )
            self.app_config = self.app_config_class(**self._config_dict)

        # env
        self.environment: Environment = self.environment_class(
            self.app_config.pyre.config.envs, self.app_config.pyre.config.env, self._config_dict, self.app_config
        )

        # dependency container
        self.dependency_container: DependencyContainer = self.dependency_container_class()

        # logging
        self.after_ = notice
        self.logging: PyreLogging = self.logging_class(config=self.app_config.logging)
        self.logger = self.logging.logger

        # extension
        self.db: Optional[SQLAlchemyDB] = None
        self.redis: Optional[Redis] = None
        self.scheduler: Optional[BackgroundScheduler] = None
        self.openapi: Optional[PyreStarletteOpenapi] = None

        # background task
        self._bg_executor = ThreadPoolExecutor(max_workers=20)

        if init_app:
            self.init_app()

    def init_app(self) -> None:
        """初始化 Pyre 框架"""

        # 1.加载配置 (Load configuration)
        self._config_dict, config_file_paths = self.config_loader.init_app(self._config_dict)

        self._config_dict = self.config_loader.safe_merge_config_dict(
            self.app_config.model_dump(mode='json', exclude_none=True, exclude_unset=True),
            self._config_dict
        )
        self.app_config = self.app_config.__class__(**self._config_dict)
        self.debug = self.app_config.server.debug or False

        # 2.重新加载环境
        self.environment = Environment(
            self.app_config.pyre.config.envs,
            self.app_config.pyre.config.env,
            self._config_dict,
            self.app_config
        )

        # 3.重新加载日志组件 (Reload logging component)
        self.logging.reconfigure(self.app_config.logging)
        self.logger = self.logging.logger

        # 5.初始化依赖注入
        self.dependency_container.inject(self)
        self.dependency_container.inject(self.state)
        self.dependency_container.inject(self.environment)
        self.dependency_container.inject(self.app_config)
        self.dependency_container.inject(self.logger)
        self.dependency_container.inject(self.logging.thread_log_handler)

        # 6.加载数据库 (Load database)
        is_init_database = False
        if self.app_config.pyre.datasource:
            self.init_database()
            self.dependency_container.inject(self.db)
            self.dependency_container.inject(self.db.snowflake)
            self.dependency_container.inject(self.db.engine)
            self.dependency_container.inject(self.db.metadata)
            is_init_database = True

        # 加载redis (Load Redis)
        if self.app_config.pyre.redis:
            self.init_redis()
            self.dependency_container.inject(self.redis)

        # 初始化任务调度
        if self.app_config.pyre.apscheduler and self.app_config.pyre.apscheduler.enable:
            self.init_apscheduler()
            self.dependency_container.inject(self.scheduler)

        # 初始化openapi
        if self.app_config.pyre.openapi.enable:
            self.init_openapi()
            self.dependency_container.inject(self.openapi)

        # 初始化依赖注入容器
        self.dependency_container.init_dependency_container()

        # 初始化调度器
        if self.scheduler:
            self.scheduler.start()

        self.router.add_route('/', self.default_index_view, summary='默认首页', include_openapi=False)
        self.after_notice(config_file_paths, is_init_database)

    def after_notice(self, config_file_paths, is_init_database):
        if not self.after_:
            return
        # 启动日志 (Startup log)
        self.logger.notice(
            f"app inited, active={self.app_config.pyre.config.env!r}, "
            f"envs={self.app_config.pyre.config.envs!r}, "
            f"config_file_path={config_file_paths}, "
            f"datacenter_id={self.app_config.sqlalchemy_db.datacenter_id}, "
            f"worker_id={self.app_config.sqlalchemy_db.worker_id}, "
            f"init_database={is_init_database}"
        )
        self.logger.notice(self.art_text)

    def add_router(
        self,
        router: Router,
        prefix: Optional[str] = None,
        name: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
        include_openapi: bool = True,
    ) -> None:
        """向应用注册路由器。"""
        self.router.add_router(
            router,
            prefix=prefix,
            name=name,
            summary=summary,
            tags=tags,
            include_openapi=include_openapi,
        )

    def controller(
        self,
        prefix: Optional[str] = '',
        name: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
        include_openapi: bool = True,
    ):
        """向应用注册控制器。"""
        return self.router.controller(
            prefix=prefix,
            name=name,
            summary=summary,
            tags=tags,
            include_openapi=include_openapi,
        )

    def init_database(self):
        """
        Initialize the SQLAlchemy database extension.
        初始化 SQLAlchemy 数据库扩展。
        """
        sql_logger = logging.getLogger('sqlalchemy.engine')
        sql_logger.propagate = False

        datasource = self.app_config.pyre.datasource
        async_mode = getattr(datasource, 'async_mode', 'auto')
        options = datasource.options or {}

        if datasource.pool_pre_ping is not None:
            options['pool_pre_ping'] = datasource.pool_pre_ping
        if datasource.pool_size is not None:
            options['pool_size'] = datasource.pool_size
        if datasource.max_overflow is not None:
            options['max_overflow'] = datasource.max_overflow
        if datasource.pool_recycle is not None:
            options['pool_recycle'] = datasource.pool_recycle
        if datasource.pool_timeout is not None:
            options['pool_timeout'] = datasource.pool_timeout

        db_config = {
            'SQLALCHEMY_DATABASE_URI': datasource.build_url(),
            'SQLALCHEMY_ECHO': datasource.echo or False,
            'SQLALCHEMY_ENGINE_OPTIONS': options,
            'SQLALCHEMY_SESSION_OPTIONS': datasource.session_options or {},
            'SQLALCHEMY_ASYNC_MODE': async_mode,
            'SNOWFLAKE_DATACENTER_ID': self.app_config.sqlalchemy_db.datacenter_id or 0,
            'SNOWFLAKE_WORKER_ID': self.app_config.sqlalchemy_db.worker_id or 0,
            'SNOWFLAKE_EPOCH': self.app_config.sqlalchemy_db.epoch,
        }

        if datasource.schemas:
            schemas = {}
            for key, schema in datasource.schemas.items():
                schemas[key] = schema.build_url()
            db_config['SQLALCHEMY_SCHEMAS'] = schemas

        self.db = self.sqlalchemy_db(async_mode=async_mode)
        self.db.init_app(db_config)

        self.add_database_middleware()

    def add_database_middleware(self):
        """
        Add database middleware to handle transaction context lifecycle.
        添加数据库中间件处理事务上下文生命周期。
        """
        if self.db is not None:
            async_mode = getattr(self.db, 'async_mode', 'auto')
            self.add_middleware(DatabaseMiddleware, db_instance=self.db, async_mode=async_mode)

    def init_redis(self):
        """
        Initialize the Redis extension.
        初始化 Redis 扩展。
        """
        try:
            from redis import Redis
        except ImportError:
            raise ImportError('请先安装 `redis` 启用 Redis')
        self.redis = Redis.from_url(url=self.app_config.pyre.redis.build_url())
        self.state['redis'] = self.redis

    def init_openapi(self):
        """
        Initialize the openapi extension.
        初始化 openapi 扩展。
        """
        self.openapi = PyreStarletteOpenapi(
            **self.app_config.pyre.openapi.model_dump(mode="json")
        )
        self.openapi.init_app(self)

    def init_apscheduler(self):
        """
        Initialize the apscheduler extension.
        初始化 apscheduler 扩展。
        """
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        except ImportError:
            raise ImportError('请先安装 `apscheduler` 启用定时任务调度')
        options = dict()

        # timezone
        if self.app_config.pyre.apscheduler.timezone:
            timezone = self.app_config.pyre.apscheduler.timezone
            self.state['APSCHEDULER_TIMEZONE'] = timezone
            options['timezone'] = timezone

        # executors
        if self.app_config.pyre.apscheduler.executors:
            executors = {
                'default': ThreadPoolExecutor(
                    self.app_config.pyre.apscheduler.executors.get('default', 20) or 20
                ),
                'processpool': ProcessPoolExecutor(
                    self.app_config.pyre.apscheduler.executors.get('processpool', 5) or 5
                )
            }
            self.state['APSCHEDULER_EXECUTORS'] = executors
            options['executors'] = executors

        # jobstores
        if self.app_config.pyre.apscheduler.jobstores:
            jobstores = {
                k: SQLAlchemyJobStore(url=e)
                for k, e in self.app_config.pyre.apscheduler.jobstores.items()
            }
            self.state['APSCHEDULER_JOBSTORES'] = jobstores
            options['jobstores'] = jobstores

        # job_defaults
        if self.app_config.pyre.apscheduler.job_defaults:
            self.state['APSCHEDULER_JOB_DEFAULTS'] = self.app_config.pyre.apscheduler.job_defaults
            options['job_defaults'] = self.app_config.pyre.apscheduler.job_defaults

        # scheduler
        self.scheduler = BackgroundScheduler(**options)

        # logger_level
        if self.app_config.pyre.apscheduler.logger_level:
            logging.getLogger('apscheduler.scheduler').setLevel(
                self.app_config.pyre.apscheduler.logger_level
            )
            logging.getLogger('apscheduler.executors.default').setLevel(
                self.app_config.pyre.apscheduler.logger_level
            )

    def get(
        self,
        rule: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Any = True,
        response_model_exclude_unset: Any = False,
        response_model_exclude_defaults: Any = False,
        include_openapi: bool = True,
        include_controller: bool = True,
        include_operation_log: bool = True,
        **options
    ):
        return self.route(
            rule=rule,
            methods=['GET'],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_controller=include_controller,
            include_operation_log=include_operation_log,
            **options
        )

    def post(
        self,
        rule: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Any = True,
        response_model_exclude_unset: Any = False,
        response_model_exclude_defaults: Any = False,
        include_openapi: Any = True,
        include_controller: bool = True,
        include_operation_log: bool = True,
        **options
    ):
        return self.route(
            rule=rule,
            methods=['POST'],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_controller=include_controller,
            include_operation_log=include_operation_log,
            **options
        )

    def put(
        self,
        rule: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Any = True,
        response_model_exclude_unset: Any = False,
        response_model_exclude_defaults: Any = False,
        include_openapi: Any = True,
        include_controller: bool = True,
        include_operation_log: bool = True,
        **options
    ):
        return self.route(
            rule=rule,
            methods=['PUT'],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_controller=include_controller,
            include_operation_log=include_operation_log,
            **options
        )

    def delete(
        self,
        rule: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Any = True,
        response_model_exclude_unset: Any = False,
        response_model_exclude_defaults: Any = False,
        include_openapi: Any = True,
        include_controller: bool = True,
        include_operation_log: bool = True,
        **options
    ):
        return self.route(
            rule=rule,
            methods=['DELETE'],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_controller=include_controller,
            include_operation_log=include_operation_log,
            **options
        )

    def patch(
        self,
        rule: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Any = True,
        response_model_exclude_unset: Any = False,
        response_model_exclude_defaults: Any = False,
        include_openapi: Any = True,
        include_controller: bool = True,
        include_operation_log: bool = True,
        **options
    ):
        return self.route(
            rule=rule,
            methods=['PATCH'],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_controller=include_controller,
            include_operation_log=include_operation_log,
            **options
        )

    def head(
        self,
        rule: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Any = True,
        response_model_exclude_unset: Any = False,
        response_model_exclude_defaults: Any = False,
        include_openapi: Any = True,
        include_controller: bool = True,
        include_operation_log: bool = True,
        **options
    ):
        return self.route(
            rule=rule,
            methods=['HEAD'],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_controller=include_controller,
            include_operation_log=include_operation_log,
            **options
        )

    def options(
        self,
        rule: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Any = True,
        response_model_exclude_unset: Any = False,
        response_model_exclude_defaults: Any = False,
        include_openapi: Any = True,
        include_controller: bool = True,
        include_operation_log: bool = True,
        **options
    ):
        """OPTIONS路由"""
        return self.route(
            rule=rule,
            methods=['OPTIONS'],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_controller=include_controller,
            include_operation_log=include_operation_log,
            **options
        )

    def route(
        self,
        rule: str,
        methods: Optional[List[str]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Any = True,
        response_model_exclude_unset: Any = False,
        response_model_exclude_defaults: Any = False,
        include_openapi: Any = True,
        include_controller: bool = True,
        include_operation_log: bool = True,
        **options
    ):
        """添加路由"""
        return self.router.route(
            rule=rule,
            methods=methods,
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_controller=include_controller,
            include_operation_log=include_operation_log,
            **options
        )

    def add_exception_handler(
        self,
        exc_class_or_status_code: int | type[Exception],
        handler: Callable[[Request, Any], Response | Awaitable[Response]],
        status_code: int = 500,
    ) -> None:
        """添加异常处理器"""
        super().add_exception_handler(
            exc_class_or_status_code,
            wrap_exception_handler(handler),
        )

    def middleware(self):
        """添加中间件"""
        def decorator(func):
            self.add_middleware(BaseHTTPMiddleware, func)
            return func

        return decorator

    def add_middleware(self, middleware_class: _MiddlewareFactory[P], *args: P.args, **kwargs: P.kwargs) -> None:
        """添加中间件"""
        if self.middleware_stack is not None:  # pragma: no cover
            raise RuntimeError("Cannot add middleware after an application has started")
        self.user_middleware.insert(1, Middleware(middleware_class, *args, **kwargs))

    def exception_handler(
        self,
        exc_class_or_status_code: int | type[Exception]
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """添加异常处理器"""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.add_exception_handler(exc_class_or_status_code, func)
            return func

        return decorator

    def add_background_task(
        self,
        func: Callable,
        *args,
        kwargs: dict = None,
        name: str = None,
        on_error: Callable[[Exception], None] = None,
    ):
        """
        添加后台任务，立即执行（与当前请求并发）。

        - 自动适配 sync/async 函数：sync 走线程池，async 走 asyncio
        - 自动适配调用上下文：async 上下文用 create_task，sync 上下文用线程池
        - 异常自动 logger.error 记录，也可通过 on_error 回调自定义处理
        - 返回 asyncio.Task(协程) 或 concurrent.futures.Future(同步)，可 cancel / add_done_callback
        """
        kwargs = kwargs or {}
        task_name = name or getattr(func, '__name__', 'background_task')

        if asyncio.iscoroutinefunction(func):
            # === async 函数 ===
            async def _wrapper():
                try:
                    return await func(*args, **kwargs)
                except asyncio.CancelledError:
                    self.logger.warning(f"后台任务被取消: {task_name}")
                    raise
                except Exception as e:
                    self.logger.error(
                        f"后台任务异常 [{task_name}]: {e}", exc_info=True
                    )
                    if on_error:
                        try:
                            on_error(e)
                        except Exception:
                            pass
                    raise

            # 尝试当前线程的 loop（async 上下文）
            try:
                loop = asyncio.get_running_loop()
                return asyncio.create_task(_wrapper(), name=task_name)
            except RuntimeError:
                # sync 上下文：没有 running loop → 在新线程中用 asyncio.run 执行
                def _run_in_thread():
                    asyncio.run(_wrapper())

                return self._bg_executor.submit(_run_in_thread)

        else:
            # === sync 函数 → 直接用线程池 ===
            def _wrapper():
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    self.logger.error(
                        f"后台任务异常 [{task_name}]: {e}", exc_info=True
                    )
                    if on_error:
                        try:
                            on_error(e)
                        except Exception:
                            pass
                    raise

            return self._bg_executor.submit(_wrapper)

    def default_index_view(self, request: Request):
        """默认首页"""
        dir = Path(__file__).resolve().parent
        welcome_html = (dir / "templates" / "welcome.html").read_text(encoding="utf-8")
        welcome_html = welcome_html.replace("{{ version }}", "1.0.0")
        welcome_html = welcome_html.replace("{{ python_version }}", platform.python_version())
        welcome_html = welcome_html.replace("{{ starlette_version }}", starlette_version)
        return HTMLResponse(content=welcome_html)

    def run(
        self,
        app: Optional[Any] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        **kwargs
    ):
        """运行"""
        import uvicorn
        host = (host or self.app_config.server.host) or '127.0.0.1'
        port = (port or self.app_config.server.port) or 8000
        uvicorn.run(app or self, host=host, port=port, **kwargs)