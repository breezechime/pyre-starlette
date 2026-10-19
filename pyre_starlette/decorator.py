from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, TypeVar

from pyre_starlette.controller import mount_controller

ROUTE_MAPPING_ATTR = "__pyre_route_mapping__"

_F = TypeVar("_F", bound=Callable[..., Any])


@dataclass
class RouteMapping:
    """Route metadata attached by mapping decorators. / mapping 装饰器附加的路由元数据。"""

    methods: List[str]
    rule: str = ""
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    status_code: Optional[int] = None
    query_model: Any = None
    body_model: Any = None
    header_model: Any = None
    cookie_model: Any = None
    response_model: Any = None
    response_model_include: Any = None
    response_model_exclude: Any = None
    response_model_by_alias: bool = True
    response_model_exclude_unset: bool = False
    response_model_exclude_defaults: bool = False
    include_openapi: bool = True
    include_controller: bool = True
    include_operation_log: bool = True
    extra_options: dict = field(default_factory=dict)


def _attach_mapping(func: _F, mapping: RouteMapping) -> _F:
    setattr(func, ROUTE_MAPPING_ATTR, mapping)
    return func


def route(
    rule: str = "",
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
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    include_openapi: bool = True,
    include_controller: bool = True,
    include_operation_log: bool = True,
    **options: Any,
) -> Callable[[_F], _F]:
    """
    Generic request mapping decorator.

    通用请求映射装饰器。
    """

    def decorator(func: _F) -> _F:
        mapping = RouteMapping(
            methods=methods or ["GET"],
            rule=rule,
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
            extra_options=options,
        )
        return _attach_mapping(func, mapping)

    return decorator


def _mount_controller_on_router(
    router: Any,
    clazz: type,
    *,
    prefix: str = "",
    name: Optional[str] = None,
    summary: Optional[str] = None,
    tags: Optional[List[str]] = None,
    include_openapi: bool = True,
) -> type:

    return mount_controller(
        router,
        clazz,
        prefix=prefix,
        name=name,
        summary=summary,
        tags=tags,
        include_openapi=include_openapi,
    )


def controller(
    rule: str = "",
    summary: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    **options: Any,
) -> Callable[[type], type]:
    router = options.pop("router", None)
    name = options.pop("name", None)
    include_openapi = options.pop("include_openapi", True)

    def decorator(clazz: type) -> type:
        default_tags = tags if tags is not None else ([summary] if summary else None)
        setattr(clazz, "__pyre_controller_prefix__", rule)
        setattr(clazz, "__pyre_controller_options__", {
            "summary": summary,
            "description": description,
            "tags": default_tags,
            **options,
        })
        if router is not None:
            _mount_controller_on_router(
                router,
                clazz,
                prefix=rule,
                name=name,
                summary=summary,
                tags=default_tags,
                include_openapi=include_openapi,
            )
        return clazz

    return decorator


def get(
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
    response_model_include: Any = None,
    response_model_exclude: Any = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    include_openapi: bool = True,
    include_controller: bool = True,
    include_operation_log: bool = True,
    **options: Any,
) -> Callable[[_F], _F]:
    """Register a GET mapping. / 注册 GET 映射。"""
    return route(
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
        response_model_include=response_model_include,
        response_model_exclude=response_model_exclude,
        response_model_by_alias=response_model_by_alias,
        response_model_exclude_unset=response_model_exclude_unset,
        response_model_exclude_defaults=response_model_exclude_defaults,
        include_openapi=include_openapi,
        include_controller=include_controller,
        include_operation_log=include_operation_log,
        **options,
    )


def post(
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
    response_model_include: Any = None,
    response_model_exclude: Any = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    include_openapi: bool = True,
    include_controller: bool = True,
    include_operation_log: bool = True,
    **options: Any,
) -> Callable[[_F], _F]:
    """Register a POST mapping. / 注册 POST 映射。"""
    return route(
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
        response_model_include=response_model_include,
        response_model_exclude=response_model_exclude,
        response_model_by_alias=response_model_by_alias,
        response_model_exclude_unset=response_model_exclude_unset,
        response_model_exclude_defaults=response_model_exclude_defaults,
        include_openapi=include_openapi,
        include_controller=include_controller,
        include_operation_log=include_operation_log,
        **options,
    )


def put(
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
    response_model_include: Any = None,
    response_model_exclude: Any = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    include_openapi: bool = True,
    include_controller: bool = True,
    include_operation_log: bool = True,
    **options: Any,
) -> Callable[[_F], _F]:
    """Register a PUT mapping. / 注册 PUT 映射。"""
    return route(
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
        response_model_include=response_model_include,
        response_model_exclude=response_model_exclude,
        response_model_by_alias=response_model_by_alias,
        response_model_exclude_unset=response_model_exclude_unset,
        response_model_exclude_defaults=response_model_exclude_defaults,
        include_openapi=include_openapi,
        include_controller=include_controller,
        include_operation_log=include_operation_log,
        **options,
    )


def delete(
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
    response_model_include: Any = None,
    response_model_exclude: Any = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    include_openapi: bool = True,
    include_controller: bool = True,
    include_operation_log: bool = True,
    **options: Any,
) -> Callable[[_F], _F]:
    """Register a DELETE mapping. / 注册 DELETE 映射。"""
    return route(
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
        response_model_include=response_model_include,
        response_model_exclude=response_model_exclude,
        response_model_by_alias=response_model_by_alias,
        response_model_exclude_unset=response_model_exclude_unset,
        response_model_exclude_defaults=response_model_exclude_defaults,
        include_openapi=include_openapi,
        include_controller=include_controller,
        include_operation_log=include_operation_log,
        **options,
    )


def patch(
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
    response_model_include: Any = None,
    response_model_exclude: Any = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    include_openapi: bool = True,
    include_controller: bool = True,
    include_operation_log: bool = True,
    **options: Any,
) -> Callable[[_F], _F]:
    """Register a PATCH mapping. / 注册 PATCH 映射。"""
    return route(
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
        response_model_include=response_model_include,
        response_model_exclude=response_model_exclude,
        response_model_by_alias=response_model_by_alias,
        response_model_exclude_unset=response_model_exclude_unset,
        response_model_exclude_defaults=response_model_exclude_defaults,
        include_openapi=include_openapi,
        include_controller=include_controller,
        include_operation_log=include_operation_log,
        **options,
    )


def head(
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
    response_model_include: Any = None,
    response_model_exclude: Any = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    include_openapi: bool = True,
    include_controller: bool = True,
    include_operation_log: bool = True,
    **options: Any,
) -> Callable[[_F], _F]:
    """Register a HEAD mapping. / 注册 HEAD 映射。"""
    return route(
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
        response_model_include=response_model_include,
        response_model_exclude=response_model_exclude,
        response_model_by_alias=response_model_by_alias,
        response_model_exclude_unset=response_model_exclude_unset,
        response_model_exclude_defaults=response_model_exclude_defaults,
        include_openapi=include_openapi,
        include_controller=include_controller,
        include_operation_log=include_operation_log,
        **options,
    )


def options(
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
    response_model_include: Any = None,
    response_model_exclude: Any = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    include_openapi: bool = True,
    include_controller: bool = True,
    include_operation_log: bool = True,
    **options: Any,
) -> Callable[[_F], _F]:
    """Register an OPTIONS mapping. / 注册 OPTIONS 映射。"""
    return route(
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
        response_model_include=response_model_include,
        response_model_exclude=response_model_exclude,
        response_model_by_alias=response_model_by_alias,
        response_model_exclude_unset=response_model_exclude_unset,
        response_model_exclude_defaults=response_model_exclude_defaults,
        include_openapi=include_openapi,
        include_controller=include_controller,
        include_operation_log=include_operation_log,
        **options,
    )


def iter_controller_members(controller_class: type) -> list[tuple[str, Any]]:
    """
    Collect controller members in definition order (subclass before bases).

    按定义顺序收集控制器成员（子类在前，基类在后）。
    """
    seen: set[str] = set()
    members: list[tuple[str, Any]] = []
    for klass in controller_class.__mro__:
        for attr_name, member in klass.__dict__.items():
            if attr_name.startswith("_") or attr_name == "router" or attr_name in seen:
                continue
            seen.add(attr_name)
            members.append((attr_name, member))
    return members


def register_mapping_routes(router: Any, controller_class: type) -> None:
    """
    Scan controller mapping decorators and register routes.

    扫描控制器上的 mapping 装饰器并注册路由。
    """
    for _attr_name, member in iter_controller_members(controller_class):
        func = member
        if isinstance(func, staticmethod):
            func = func.__func__
        elif isinstance(func, classmethod):
            func = func.__func__
        mapping: RouteMapping | None = getattr(func, ROUTE_MAPPING_ATTR, None)
        if mapping is None:
            continue
        router.route(
            rule=mapping.rule,
            methods=mapping.methods,
            summary=mapping.summary,
            description=mapping.description,
            tags=mapping.tags,
            status_code=mapping.status_code,
            query_model=mapping.query_model,
            body_model=mapping.body_model,
            header_model=mapping.header_model,
            cookie_model=mapping.cookie_model,
            response_model=mapping.response_model,
            response_model_include=mapping.response_model_include,
            response_model_exclude=mapping.response_model_exclude,
            response_model_by_alias=mapping.response_model_by_alias,
            response_model_exclude_unset=mapping.response_model_exclude_unset,
            response_model_exclude_defaults=mapping.response_model_exclude_defaults,
            include_openapi=mapping.include_openapi,
            include_controller=mapping.include_controller,
            include_operation_log=mapping.include_operation_log,
            **mapping.extra_options,
        )(func)
