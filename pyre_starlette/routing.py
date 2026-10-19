import copy
import inspect
import typing
from functools import wraps
from inspect import _empty, signature
from typing import Annotated, Any, Callable, List, Optional, Type, get_args, get_origin

from pydantic import BaseModel, ValidationError
from starlette import routing
from starlette._utils import is_async_callable
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, compile_path, get_name
from starlette.types import ASGIApp, Lifespan

from pydantic_core import PydanticUndefined

from pyre_injector import autowired
from pyre_injector.constants import INJECT_DEPEND_KEY
from pyre_starlette.exceptions.exceptions import BadRequestException, RequestValidationError

from .responses import build_response
from .decorator import register_mapping_routes
from .params import (
    BodyInfo,
    CookieInfo,
    HeaderInfo,
    PathInfo,
    QueryInfo,
    header_lookup_key,
    resolve_annotated_param,
    validate_model_param,
    validate_param_value,
)
from .requests import with_request_context


class Route(routing.Route):
    """Pyre Starlette Route class"""

    def __init__(
        self,
        path: str,
        endpoint: typing.Callable[..., typing.Any],
        *,
        methods: typing.Optional[typing.List[str]] = None,
        name: typing.Optional[str] = None,
        include_in_schema: bool = True,
        middleware: typing.Optional[typing.Sequence[Middleware]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = 200,
        query_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        body_model: Any = None,
        response_model: Any = None,
        validate_response_model: bool = True,
        responses: Any = None,
        response_description: str = "Request Service Success",
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: bool = True,
        response_model_exclude_none: bool = False,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        include_openapi: bool = True,
        include_operation_log: bool = True,
        endpoint_name: Optional[str] = None,
        is_staticmethod: bool = True,
        controller_class: Optional[Type[Any]] = None,
        origin_path: Optional[str] = None,
        **options: Any,
    ) -> None:
        self.func = endpoint
        self.origin_path = origin_path if origin_path is not None else path
        self.path = path
        self.summary = summary
        self.description = description
        self.tags = tags or []
        self.status_code = status_code or 200
        self.query_model = query_model
        self.header_model = header_model
        self.cookie_model = cookie_model
        self.body_model = body_model
        self.response_model = response_model
        self.validate_response_model = validate_response_model
        self.responses = responses
        self.response_description = response_description
        self.response_model_include = response_model_include
        self.response_model_exclude = response_model_exclude
        self.response_model_by_alias = response_model_by_alias
        self.response_model_exclude_none = response_model_exclude_none
        self.response_model_exclude_unset = response_model_exclude_unset
        self.response_model_exclude_defaults = response_model_exclude_defaults
        self.include_openapi = include_openapi
        self.include_operation_log = include_operation_log
        self.options = options or {}
        self.endpoint_name = endpoint_name
        self.is_staticmethod = is_staticmethod
        self.controller_class = controller_class

        if isinstance(self.tags, str):
            self.tags = self.tags.split(",")

        handler = with_request_context(self.get_route_handler())
        super().__init__(
            path=path,
            endpoint=handler,
            methods=methods,
            name=name or endpoint_name,
            include_in_schema=include_openapi,
            middleware=middleware,
        )

    def get_route_handler(self) -> Callable[[Request], Any]:
        """Return the request handler for this route."""
        return get_request_handler(self)

    def __repr__(self) -> str:
        methods = sorted(self.methods or [])
        return (
            f"{self.__class__.__name__}("
            f"path={self.path!r}, "
            f"name={self.name!r}, "
            f"methods={methods!r}, "
            f"summary={self.summary!r}, "
            f"description={self.description!r})"
        )

    def copy(self) -> "Route":
        """Return a shallow copy of this route. / 返回当前路由的浅拷贝。"""
        route = copy.copy(self)
        route.endpoint_name = None
        return route

    def generate_endpoint(
        self,
        router_name: Optional[str] = None,
        parent_router_name: Optional[str] = None,
        router_controller_name: Optional[str] = None,
        rule: Optional[str] = None,
    ) -> str:
        """Generate endpoint name for this route. / 为当前路由生成 endpoint 名称。"""
        return generate_endpoint_name(
            self.func,
            rule or self.path,
            router_name=router_name,
            parent_router_name=parent_router_name,
            router_controller_name=router_controller_name,
        )


class Router(routing.Router):
    """
    Pyre router class, used to group path operations.

    Register it on the application with `add_router`, or define routes directly on the
    root router.

    Pyre 路由器，用于分组管理路径操作。

    通过 `add_router` 挂载到应用，或直接在根 router 上声明路由。
    """

    def __init__(
        self,
        prefix: str = "",
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None,
        name: Optional[str] = None,
        responses: Any = None,
        response_description: Optional[str] = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: bool = True,
        response_model_exclude_none: bool = False,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        include_openapi: bool = True,
        include_operation_log: bool = True,
        routes: typing.Optional[typing.Sequence[BaseRoute]] = None,
        redirect_slashes: bool = True,
        default: typing.Optional[ASGIApp] = None,
        lifespan: typing.Optional[Lifespan[typing.Any]] = None,
        *,
        route_class: type[Route] = Route,
        controller_class: Optional[Type[Any]] = None,
        **kwargs: Any,
    ) -> None:
        self.prefix = prefix or ""
        self.name = name
        self.tags = tags or []
        self.summary = summary
        self.responses = responses
        self.response_description = response_description
        self.response_model_include = response_model_include
        self.response_model_exclude = response_model_exclude
        self.response_model_by_alias = response_model_by_alias
        self.response_model_exclude_none = response_model_exclude_none
        self.response_model_exclude_unset = response_model_exclude_unset
        self.response_model_exclude_defaults = response_model_exclude_defaults
        self.route_class = route_class
        self.include_openapi = include_openapi
        self.include_operation_log = include_operation_log
        self.controller_class = controller_class
        self.sub_routers: dict[str, "Router"] = {}
        self.parent_router: Optional["Router"] = None
        super().__init__(
            routes=routes,
            redirect_slashes=redirect_slashes,
            default=default,
            lifespan=lifespan,
            **kwargs,
        )

    def add_route(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
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
        responses: Any = None,
        response_description: Optional[str] = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Optional[bool] = None,
        response_model_exclude_none: Optional[bool] = None,
        response_model_exclude_unset: Optional[bool] = None,
        response_model_exclude_defaults: Optional[bool] = None,
        include_openapi: Optional[bool] = None,
        include_operation_log: Optional[bool] = None,
        name: Optional[str] = None,
        route_class_override: Optional[type[Route]] = None,
        controller_class: Optional[Type[Any]] = None,
        **options: Any,
    ) -> None:
        """
        Register a path operation on this router.

        在当前 router 上注册路径操作。
        """
        summary = summary if summary is not None else self.summary
        responses = responses if responses is not None else self.responses
        response_description = (
            response_description if response_description is not None else self.response_description
        )
        response_model_include = (
            response_model_include if response_model_include is not None else self.response_model_include
        )
        response_model_exclude = (
            response_model_exclude if response_model_exclude is not None else self.response_model_exclude
        )
        response_model_by_alias = (
            self.response_model_by_alias if response_model_by_alias is None else response_model_by_alias
        )
        response_model_exclude_none = (
            self.response_model_exclude_none if response_model_exclude_none is None else response_model_exclude_none
        )
        response_model_exclude_unset = (
            self.response_model_exclude_unset if response_model_exclude_unset is None else response_model_exclude_unset
        )
        response_model_exclude_defaults = (
            self.response_model_exclude_defaults
            if response_model_exclude_defaults is None
            else response_model_exclude_defaults
        )
        include_openapi = self.include_openapi if include_openapi is None else include_openapi
        include_operation_log = (
            self.include_operation_log if include_operation_log is None else include_operation_log
        )

        current_tags = list(self.tags)
        if tags:
            current_tags.extend(tags if isinstance(tags, list) else [tags])
        route_class = route_class_override or self.route_class
        origin_path = path or ""
        full_path = join_paths(self.prefix, origin_path)
        endpoint_name = name or options.pop("name", None) or options.pop("endpoint", None)
        if not endpoint_name:
            endpoint_name = generate_endpoint_name(
                endpoint,
                origin_path,
                router_name=self.name,
            )

        route = route_class(
            path=full_path,
            origin_path=origin_path,
            endpoint=endpoint,
            methods=methods or ["GET"],
            name=endpoint_name,
            summary=summary,
            description=description,
            tags=current_tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            responses=responses,
            response_description=response_description or "Request Service Success",
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_operation_log=include_operation_log,
            endpoint_name=endpoint_name,
            controller_class=controller_class or self.controller_class,
            **options,
        )
        self._finalize_route(route, self)
        self.routes.append(route)

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
        responses: Any = None,
        response_description: Optional[str] = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Optional[bool] = None,
        response_model_exclude_none: Optional[bool] = None,
        response_model_exclude_unset: Optional[bool] = None,
        response_model_exclude_defaults: Optional[bool] = None,
        include_openapi: Optional[bool] = None,
        include_operation_log: Optional[bool] = None,
        route_class_override: Optional[type[Route]] = None,
        **options: Any,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        Register a path operation decorator.

        路径操作装饰器。
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.add_route(
                rule,
                func,
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
                responses=responses,
                response_description=response_description,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_none=response_model_exclude_none,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                include_openapi=include_openapi,
                include_operation_log=include_operation_log,
                route_class_override=route_class_override,
                **options,
            )
            return func

        return decorator

    def controller(
        self,
        prefix: Optional[str] = "",
        name: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
        include_openapi: bool = True,
    ) -> Callable[[Type[Any]], Type[Any]]:
        """
        Register a controller class and mount its routes.

        注册控制器类并挂载其路由。
        """

        def decorator(clazz: Type[Any]) -> Type[Any]:
            controller_prefix = getattr(clazz, "__pyre_controller_prefix__", None)
            controller_options = getattr(clazz, "__pyre_controller_options__", {})
            merged_prefix = prefix if prefix is not None else (controller_prefix or "")
            merged_summary = summary or controller_options.get("summary")
            merged_tags = list(tags or controller_options.get("tags") or [])
            if not merged_tags and merged_summary:
                merged_tags = [merged_summary]

            sub_router = Router(
                prefix=merged_prefix or "",
                name=name,
                summary=merged_summary,
                tags=merged_tags,
                responses=self.responses,
                response_description=self.response_description,
                response_model_include=self.response_model_include,
                response_model_exclude=self.response_model_exclude,
                response_model_by_alias=self.response_model_by_alias,
                response_model_exclude_none=self.response_model_exclude_none,
                response_model_exclude_unset=self.response_model_exclude_unset,
                response_model_exclude_defaults=self.response_model_exclude_defaults,
                include_openapi=include_openapi,
                include_operation_log=self.include_operation_log,
                route_class=self.route_class,
                controller_class=clazz,
            )
            clazz.router = sub_router

            register_mapping_routes(sub_router, clazz)
            self._adopt_controller_routes(sub_router, clazz)
            self.add_router(sub_router)
            return clazz

        return decorator

    def add_router(
        self,
        router: "Router",
        prefix: Optional[str] = None,
        name: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
        include_openapi: bool = True,
    ) -> None:
        """
        Include another router in this router.

        挂载子路由器。
        """
        if self.parent_router is router:
            raise RuntimeError("父级路由器不能挂载自身")

        if prefix is not None:
            router.prefix = join_paths(prefix, router.prefix)
        if name is not None:
            router.name = name
        if summary is not None:
            router.summary = summary
        if tags is not None:
            router.tags = tags
        router.parent_router = self
        router.include_openapi = include_openapi

        router_name = self.format_name(router.name, router.prefix)
        router.name = router_name
        if isinstance(router.tags, str):
            router.tags = router.tags.split(",")

        if router_name in self.sub_routers and self.sub_routers[router_name] is not router:
            raise ValueError(
                f"Router name '{router_name}' is already registered. "
                f"Use name= to provide a unique name."
            )
        self.sub_routers[router_name] = router
        include_prefix = join_paths(self.prefix, prefix if prefix is not None else "")
        for route in router.routes:
            if not isinstance(route, Route):
                continue
            route.path = join_paths(include_prefix, route.path)
            self._finalize_route(route, router)
            if route not in self.routes:
                self.routes.append(route)

    def get_route(self, name: str) -> Optional[Route]:
        """Get a route by endpoint name. / 按 endpoint 名称获取路由。"""
        for route in self.iter_routes():
            if route.name == name:
                return route
        return None

    def iter_routes(self) -> list[Route]:
        """
        Iterate Pyre routes registered on this router.

        遍历当前 router 上注册的全部 Pyre Route。
        """
        return [route for route in self.routes if isinstance(route, Route)]

    def _finalize_route(self, route: Route, owner: "Router") -> None:
        """Compile path and apply owner metadata. / 编译路径并写入所属 router 元数据。"""
        route.path_regex, route.path_format, route.param_convertors = compile_path(route.path)

        if owner.controller_class:
            route.controller_class = owner.controller_class
            route.is_staticmethod = is_controller_staticmethod(owner.controller_class, route.func)

        if not route.endpoint_name:
            parent_name = owner.parent_router.name if owner.parent_router else ""
            route.endpoint_name = route.generate_endpoint(
                router_name=owner.name,
                parent_router_name=parent_name or "",
                router_controller_name=owner.controller_class.__name__ if owner.controller_class else None,
                rule=route.origin_path,
            )
            route.name = route.endpoint_name

    def _adopt_controller_routes(self, controller_router: "Router", controller_class: Type[Any]) -> None:
        """
        Move routes belonging to a controller from the parent router into its sub-router.

        将父 router 上属于该 controller 的路由移入 controller 子 router。
        """
        members = controller_callables(controller_class)
        for route in list(self.routes):
            if not isinstance(route, Route):
                continue
            member = members.get(route.func)
            if member is None:
                continue
            self.routes.remove(route)
            route.controller_class = controller_class
            route.is_staticmethod = isinstance(member, staticmethod)
            controller_router.routes.append(route)

    @staticmethod
    def format_name(name: Optional[str], prefix: str) -> str:
        """Build a stable router name from `name` or `prefix`. / 根据 name 或 prefix 生成 router 名称。"""
        if not name:
            name = (prefix or "").replace("/", "_").lstrip("_").rstrip("_")
        if name and name.startswith("."):
            name = name[1:]
        if name and name.endswith("."):
            name = name[:-1]
        return name or "router"

    def get(
        self,
        rule: str = "",
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        responses: Any = None,
        response_description: Optional[str] = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Optional[bool] = None,
        response_model_exclude_none: Optional[bool] = None,
        response_model_exclude_unset: Optional[bool] = None,
        response_model_exclude_defaults: Optional[bool] = None,
        include_openapi: Optional[bool] = None,
        include_operation_log: Optional[bool] = None,
        **options: Any,
    ):
        """Register a GET path operation. / 注册 GET 路径操作。"""
        return self.route(
            rule=rule,
            methods=["GET"],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            responses=responses,
            response_description=response_description,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_operation_log=include_operation_log,
            **options,
        )

    def post(
        self,
        rule: str = "",
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        responses: Any = None,
        response_description: Optional[str] = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Optional[bool] = None,
        response_model_exclude_none: Optional[bool] = None,
        response_model_exclude_unset: Optional[bool] = None,
        response_model_exclude_defaults: Optional[bool] = None,
        include_openapi: Optional[bool] = None,
        include_operation_log: Optional[bool] = None,
        **options: Any,
    ):
        """Register a POST path operation. / 注册 POST 路径操作。"""
        return self.route(
            rule=rule,
            methods=["POST"],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            responses=responses,
            response_description=response_description,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_operation_log=include_operation_log,
            **options,
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
        responses: Any = None,
        response_description: Optional[str] = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Optional[bool] = None,
        response_model_exclude_none: Optional[bool] = None,
        response_model_exclude_unset: Optional[bool] = None,
        response_model_exclude_defaults: Optional[bool] = None,
        include_openapi: Optional[bool] = None,
        include_operation_log: Optional[bool] = None,
        **options: Any,
    ):
        """Register a PUT path operation. / 注册 PUT 路径操作。"""
        return self.route(
            rule=rule,
            methods=["PUT"],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            responses=responses,
            response_description=response_description,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_operation_log=include_operation_log,
            **options,
        )

    def delete(
        self,
        rule: str = "",
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status_code: Optional[int] = None,
        query_model: Any = None,
        body_model: Any = None,
        header_model: Any = None,
        cookie_model: Any = None,
        response_model: Any = None,
        responses: Any = None,
        response_description: Optional[str] = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Optional[bool] = None,
        response_model_exclude_none: Optional[bool] = None,
        response_model_exclude_unset: Optional[bool] = None,
        response_model_exclude_defaults: Optional[bool] = None,
        include_openapi: Optional[bool] = None,
        include_operation_log: Optional[bool] = None,
        **options: Any,
    ):
        """Register a DELETE path operation. / 注册 DELETE 路径操作。"""
        return self.route(
            rule=rule,
            methods=["DELETE"],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            responses=responses,
            response_description=response_description,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_operation_log=include_operation_log,
            **options,
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
        responses: Any = None,
        response_description: Optional[str] = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Optional[bool] = None,
        response_model_exclude_none: Optional[bool] = None,
        response_model_exclude_unset: Optional[bool] = None,
        response_model_exclude_defaults: Optional[bool] = None,
        include_openapi: Optional[bool] = None,
        include_operation_log: Optional[bool] = None,
        **options: Any,
    ):
        """Register a PATCH path operation. / 注册 PATCH 路径操作。"""
        return self.route(
            rule=rule,
            methods=["PATCH"],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            responses=responses,
            response_description=response_description,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_operation_log=include_operation_log,
            **options,
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
        responses: Any = None,
        response_description: Optional[str] = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Optional[bool] = None,
        response_model_exclude_none: Optional[bool] = None,
        response_model_exclude_unset: Optional[bool] = None,
        response_model_exclude_defaults: Optional[bool] = None,
        include_openapi: Optional[bool] = None,
        include_operation_log: Optional[bool] = None,
        **options: Any,
    ):
        """Register a HEAD path operation. / 注册 HEAD 路径操作。"""
        return self.route(
            rule=rule,
            methods=["HEAD"],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            responses=responses,
            response_description=response_description,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_operation_log=include_operation_log,
            **options,
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
        responses: Any = None,
        response_description: Optional[str] = None,
        response_model_include: Any = None,
        response_model_exclude: Any = None,
        response_model_by_alias: Optional[bool] = None,
        response_model_exclude_none: Optional[bool] = None,
        response_model_exclude_unset: Optional[bool] = None,
        response_model_exclude_defaults: Optional[bool] = None,
        include_openapi: Optional[bool] = None,
        include_operation_log: Optional[bool] = None,
        **options: Any,
    ):
        """Register an OPTIONS path operation. / 注册 OPTIONS 路径操作。"""
        return self.route(
            rule=rule,
            methods=["OPTIONS"],
            summary=summary,
            description=description,
            tags=tags,
            status_code=status_code,
            query_model=query_model,
            body_model=body_model,
            header_model=header_model,
            cookie_model=cookie_model,
            response_model=response_model,
            responses=responses,
            response_description=response_description,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_none=response_model_exclude_none,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            include_openapi=include_openapi,
            include_operation_log=include_operation_log,
            **options,
        )


# ---------------------------------------------------------------------------
# Route utilities
# 路由工具
# ---------------------------------------------------------------------------


def join_paths(*parts: str) -> str:
    """Join URL path segments. / 拼接 URL 路径片段。"""
    segments = [part.strip("/") for part in parts if part and part.strip("/")]
    return "/" + "/".join(segments) if segments else "/"


def generate_endpoint_name(
    func: Callable[..., Any],
    rule: str,
    router_name: Optional[str] = None,
    parent_router_name: Optional[str] = None,
    router_controller_name: Optional[str] = None,
) -> str:
    """Generate a stable endpoint name from router context. / 根据 router 上下文生成 endpoint 名称。"""
    router_name = router_name or ""
    parent_router_name = parent_router_name or ""
    endpoint = f"{parent_router_name}.{router_name}"
    if router_controller_name:
        endpoint = f"{endpoint}.{router_controller_name}"
    endpoint = f"{endpoint}.{get_name(func)}_{rule.replace('/', '_')}"
    return endpoint.replace("__", "_").lstrip(".").rstrip("_").lstrip("_")


def normalize_path(prefix: str, rule: str) -> str:
    """Combine prefix and rule into a full path. / 将 prefix 与 rule 合并为完整路径。"""
    return join_paths(prefix, rule)


def unwrap_callable(member: Any) -> Any:
    """Unwrap staticmethod/classmethod to the underlying function. / 解包 staticmethod/classmethod。"""
    if isinstance(member, staticmethod):
        return member.__func__
    if isinstance(member, classmethod):
        return member.__func__
    return member


def controller_callables(controller_class: Type[Any]) -> dict[Any, Any]:
    """Collect callable members from a controller class. / 收集控制器类中的可调用成员。"""
    members: dict[Any, Any] = {}
    for attr_name, member in controller_class.__dict__.items():
        if attr_name.startswith("_") or attr_name == "router":
            continue
        func = unwrap_callable(member)
        if inspect.isfunction(func):
            members[func] = member
    return members


def is_controller_staticmethod(controller_class: Type[Any], func: Callable[..., Any]) -> bool:
    """Check whether a controller method is a staticmethod. / 判断控制器方法是否为 staticmethod。"""
    for member in controller_class.__dict__.values():
        if unwrap_callable(member) is func:
            return isinstance(member, staticmethod)
    return False


def get_path_param_names(path: str) -> list[str]:
    """Return path parameter names from a Starlette path. / 从 Starlette 路径提取参数名。"""
    _, _, param_convertors = compile_path(path)
    return list(param_convertors.keys())


def accepts_request_parameter(func: Callable[..., Any]) -> tuple[bool, str | None]:
    """Detect whether the endpoint accepts a `Request` parameter. / 检测 endpoint 是否接受 `Request` 参数。"""
    for name, param in signature(func).parameters.items():
        if param.annotation is Request:
            return True, name
    return False, None


def is_request_annotation(annotation: Any) -> bool:
    """Return True if the annotation is `Request`. / 判断注解是否为 `Request`。"""
    return annotation is Request


# ---------------------------------------------------------------------------
# Request handling / injection
# 请求处理 / 注入
# ---------------------------------------------------------------------------


async def read_body_dict(request: Request) -> Any:
    """Read and parse the request body into a dict. / 读取并解析请求体为 dict。"""
    content_type = request.headers.get("content-type", "")
    if not content_type:
        try:
            return await request.json()
        except Exception:
            return {}
    if "application/json" in content_type or content_type.endswith("+json"):
        try:
            return await request.json()
        except Exception as exc:
            raise BadRequestException(msg="请求体不是合法 JSON") from exc
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        return dict(form)
    return {}


def _needs_body(route: Route, func_parameters: dict[str, Any]) -> bool:
    return any(
        param.annotation is route.body_model
        or (
            get_origin(param.annotation) is Annotated
            and isinstance(get_args(param.annotation)[1], BodyInfo)
        )
        for param in func_parameters.values()
    )


def declared_default(func_param: Any, meta: Any) -> tuple[Any, bool]:
    """Return the default declared on ``Annotated[..., Query(default=...)]`` or the signature."""
    if meta is not None:
        default = getattr(meta, "default", PydanticUndefined)
        if default is not PydanticUndefined:
            return default, True
    if func_param.default is not _empty:
        return func_param.default, True
    return None, False


def resolve_single_param(
    func_param: Any,
    meta: Any,
    inner: Any,
    value: Any,
    *,
    present: bool,
    key: str,
) -> Any:
    """Validate a single non-model parameter, falling back to its declared default when absent."""
    if not present:
        default, has_default = declared_default(func_param, meta)
        if has_default:
            return default
    return validate_param_value(inner, value, key=key)


def resolve_handler_kwargs(
    request: Request,
    route: Route,
    func: Callable[..., Any],
    *,
    body_dict: Any | None = None,
) -> dict[str, Any]:
    """
    Resolve keyword arguments for the endpoint from the request.

    根据请求解析 endpoint 的 kwargs（路径、Query、Body、Header、Cookie、依赖注入等）。
    """
    path_param_names = get_path_param_names(route.path)
    query_dict = dict(request.query_params)
    body_dict = {} if body_dict is None else body_dict

    func_parameters = signature(func).parameters
    defer_body = _needs_body(route, func_parameters) and body_dict is None

    kwargs: dict[str, Any] = {}
    skip_instance = route.controller_class is not None and not route.is_staticmethod

    for key, func_param in func_parameters.items():
        if is_request_annotation(func_param.annotation):
            continue
        if skip_instance and key == "self":
            continue

        if key in path_param_names:
            kwargs[key] = validate_param_value(
                func_param.annotation,
                request.path_params[key],
                key=key
            )
            continue

        try:
            if route.query_model is not None and func_param.annotation is route.query_model:
                kwargs[key] = route.query_model.model_validate(query_dict)
                continue
            if route.body_model is not None and func_param.annotation is route.body_model:
                if not defer_body:
                    kwargs[key] = route.body_model.model_validate(body_dict or {})
                continue
            if route.header_model is not None and func_param.annotation is route.header_model:
                kwargs[key] = route.header_model.model_validate(dict(request.headers))
                continue
            if route.cookie_model is not None and func_param.annotation is route.cookie_model:
                kwargs[key] = route.cookie_model.model_validate(dict(request.cookies))
                continue
        except ValidationError as e:
            exc = RequestValidationError.from_exception_data(
                title=e.title,
                line_errors=e.errors(),
            )
            exc.key = key  # type: ignore[attr-defined]
            raise exc

        annotation = func_param.annotation if func_param.annotation is not _empty else Any
        inner, meta = resolve_annotated_param(annotation)
        values = query_dict

        if meta is not None:
            if isinstance(meta, QueryInfo):
                values = query_dict
            elif isinstance(meta, BodyInfo):
                if defer_body:
                    continue
                values = body_dict if isinstance(body_dict, dict) else {}
            elif isinstance(meta, HeaderInfo):
                header_key = header_lookup_key(key, meta)
                present = header_key in request.headers
                kwargs[key] = resolve_single_param(
                    func_param,
                    meta,
                    inner,
                    request.headers.get(header_key),
                    present=present,
                    key=key,
                )
                continue
            elif isinstance(meta, CookieInfo):
                kwargs[key] = resolve_single_param(
                    func_param,
                    meta,
                    inner,
                    request.cookies.get(key),
                    present=key in request.cookies,
                    key=key,
                )
                continue
            elif isinstance(meta, PathInfo):
                kwargs[key] = resolve_single_param(
                    func_param,
                    meta,
                    inner,
                    request.path_params.get(key),
                    present=key in request.path_params,
                    key=key,
                )
                continue

        if hasattr(inner, INJECT_DEPEND_KEY):
            kwargs[key] = autowired(inner)
        elif isinstance(inner, type) and issubclass(inner, BaseModel):
            source = values if isinstance(values, dict) else {}
            kwargs[key] = validate_model_param(inner, source, key=key)
        else:
            kwargs[key] = resolve_single_param(
                func_param,
                meta,
                inner,
                values.get(key),
                present=key in values,
                key=key,
            )

    return kwargs


async def resolve_handler_kwargs_async(
    request: Request,
    route: Route,
    func: Callable[..., Any],
) -> dict[str, Any]:
    """Async wrapper that reads body before resolving kwargs. / 异步读取 body 后解析 kwargs。"""
    func_parameters = signature(func).parameters
    if _needs_body(route, func_parameters) and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        body_dict = await read_body_dict(request)
    else:
        body_dict = {}
    kwargs = resolve_handler_kwargs(request, route, func, body_dict=body_dict)

    if body_dict and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        for key, func_param in func_parameters.items():
            if route.body_model is not None and func_param.annotation is route.body_model:
                try:
                    kwargs[key] = route.body_model.model_validate(body_dict if isinstance(body_dict, dict) else {})
                except ValidationError as e:
                    exc = RequestValidationError.from_exception_data(
                        title=e.title,
                        line_errors=e.errors(),
                    )
                    exc.key = key  # type: ignore[attr-defined]
                    raise exc
                continue
            annotation = func_param.annotation if func_param.annotation is not _empty else Any
            inner, meta = resolve_annotated_param(annotation)
            if isinstance(meta, BodyInfo) and isinstance(inner, type) and issubclass(inner, BaseModel):
                source = body_dict if isinstance(body_dict, dict) else {}
                kwargs[key] = validate_model_param(inner, source, key=key)
    return kwargs


def get_request_handler(route: Route) -> Callable[[Request], Any]:
    """
    Build the request handler for a route.

    Handles parameter injection, endpoint invocation, and response serialization.

    构建 Route 的请求 handler。

    负责参数注入、调用 endpoint 以及响应序列化。
    """
    func = route.func
    accepts_request, request_name = accepts_request_parameter(func)

    def run_auth_precheck() -> None:
        precheck = getattr(func, "__pyre_auth_precheck__", None)
        if callable(precheck):
            precheck()

    def build_call_args() -> list[Any]:
        if route.controller_class and not route.is_staticmethod:
            return [autowired(route.controller_class)]
        return []

    # is async handler
    if is_async_callable(func):
        @wraps(func)
        async def async_handler(request: Request) -> Response:
            run_auth_precheck()
            kwargs = await resolve_handler_kwargs_async(request, route, func)
            call_args = build_call_args()
            if accepts_request:
                kwargs[request_name] = request
            response = await func(*call_args, **kwargs)
            return build_response(
                response, 
                status_code=route.status_code, 
                exclude=route.response_model_exclude, 
                include=route.response_model_include, 
                exclude_none=route.response_model_exclude_none, 
                exclude_unset=route.response_model_exclude_unset, 
                exclude_defaults=route.response_model_exclude_defaults, 
                by_alias=route.response_model_by_alias, 
                validate_response_model=route.validate_response_model, 
                response_model=route.response_model
            )

        return async_handler

    # is sync handler
    @wraps(func)
    async def sync_handler(request: Request) -> Response:
        run_auth_precheck()
        kwargs = await resolve_handler_kwargs_async(request, route, func)

        def invoke() -> Any:
            call_args = build_call_args()
            if accepts_request:
                kwargs[request_name] = request
            return func(*call_args, **kwargs)

        response = await run_in_threadpool(invoke)
        return build_response(
            response,
            status_code=route.status_code, 
            exclude=route.response_model_exclude, 
            include=route.response_model_include, 
            exclude_none=route.response_model_exclude_none, 
            exclude_unset=route.response_model_exclude_unset, 
            exclude_defaults=route.response_model_exclude_defaults, 
            by_alias=route.response_model_by_alias, 
            validate_response_model=route.validate_response_model, 
            response_model=route.response_model
        )

    return sync_handler
