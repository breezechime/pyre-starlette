from typing import Any, ClassVar, List, Optional, Type, TypeVar

from pyre_injector import DependencyContainer, DependencyDefinition, autowired

from .middleware import Middleware

_T = TypeVar("_T", bound="Controller")


def register_controller_bean(clazz: Type[Any]) -> None:
    """将控制器类注册到 DI 容器（由 ``@router.controller`` / ``@controller_mapping`` 调用）。"""
    bean_definition = DependencyDefinition.parse_dependency(clazz)
    if clazz.__name__ not in DependencyContainer.dependency_definitions:
        DependencyContainer.register_dependency_definition(
            clazz.__name__, bean_definition, solve_init=False
        )


def mount_controller(
    parent_router: Any,
    clazz: Type[Any],
    *,
    prefix: Optional[str] = "",
    name: Optional[str] = None,
    summary: Optional[str] = None,
    tags: Optional[List[str]] = None,
    include_openapi: bool = True,
) -> Type[Any]:
    """挂载控制器类到路由器并注册路由。"""
    from .decorator import register_mapping_routes
    from .routing import Router

    register_controller_bean(clazz)

    controller_prefix = getattr(clazz, "__pyre_controller_prefix__", None)
    controller_options = getattr(clazz, "__pyre_controller_options__", {})
    merged_prefix = prefix if prefix is not None else (controller_prefix or "")
    merged_summary = summary or controller_options.get("summary")
    merged_tags = list(tags or controller_options.get("tags") or [])

    sub_router = Router(
        prefix=merged_prefix or "",
        name=name,
        summary=merged_summary,
        tags=merged_tags,
        responses=parent_router.responses,
        response_description=parent_router.response_description,
        response_model_include=parent_router.response_model_include,
        response_model_exclude=parent_router.response_model_exclude,
        response_model_by_alias=parent_router.response_model_by_alias,
        response_model_exclude_none=parent_router.response_model_exclude_none,
        response_model_exclude_unset=parent_router.response_model_exclude_unset,
        response_model_exclude_defaults=parent_router.response_model_exclude_defaults,
        include_openapi=include_openapi,
        include_operation_log=parent_router.include_operation_log,
        route_class=parent_router.route_class,
        controller_class=clazz,
    )
    clazz.router = sub_router

    register_mapping_routes(sub_router, clazz)
    parent_router._adopt_controller_routes(sub_router, clazz)
    parent_router.add_router(sub_router)
    return clazz


class Controller:
    """控制器 Mixin（可选继承）。

    - **不必继承**本类即可编写控制器；``@router.controller`` 或
      ``@controller_mapping(router=...)`` 会负责 DI 注册与路由挂载。
    - 仅在需要 ``before_request`` / ``after_request`` / ``middlewares`` 时继承。
    """

    middlewares: ClassVar[List[Middleware]] = []
    init_every_request: ClassVar[bool] = True
    router: ClassVar[Any | None] = None

    def autowired(self, depend: type[_T]) -> _T:
        """在控制器内手动获取依赖。"""
        return autowired(depend)

    def before_request(self, **kwargs):
        """子类可覆写：每个请求前调用。"""

    def after_request(self, response):
        """子类可覆写：每个请求后调用。"""
        return response
