import enum
from typing import Callable, Optional, Type, TypeVar, Union

from pydantic import BaseModel
from sqlalchemy import Column
from sqlalchemy.orm import DeclarativeBase

from pyre_injector import DependencyContainer, DependencyDefinition, provider
from .exceptions import BadRequestException, HTTPException, NotFoundDataException

_T = TypeVar("_T")


class BaseService:
    """基础业务"""

    model_class = None

    def __init_subclass__(cls, **kwargs):
        bean_definition = DependencyDefinition.parse_dependency(cls)
        if cls.__name__ not in DependencyContainer.dependency_definitions:
            DependencyContainer.register_dependency_definition(cls.__name__, bean_definition)
        return super().__init_subclass__(**kwargs)

    def provider(self, depend: Union[str, Type[_T]]) -> _T:
        """手动获取已注册的依赖。"""
        return provider(depend)

    def add_background_task(
        self,
        job: Callable,
        *args,
        kwargs=None,
        name: str = None,
        on_error: Callable[[Exception], None] = None,
    ):
        """添加后台任务，立即执行。自动适配 sync/async 函数和调用上下文。"""
        from .app import PyreStarlette
        return self.provider(PyreStarlette).add_background_task(
            job, *args, kwargs=kwargs, name=name, on_error=on_error
        )

    def service_general_save(self, params: BaseModel, save: bool = True):
        """通用业务保存。"""
        model = self.model_class.query.get_by_id(params.id)
        if params.id and not model:
            raise NotFoundDataException()
        if model is None:
            params.id = None
            model = self.model_class()
        model.from_entity(params)
        if save:
            model = model.save()
        return model

    def service_filter(
        self,
        data: Union[BaseModel, dict],
        model_class: Optional[DeclarativeBase] = None,
        include: Optional[Union[set, dict]] = None,
        exclude: Optional[Union[set, dict]] = None,
        custom_filter: Optional[Callable] = None,
        perfect: bool = False,
    ) -> list:
        """业务筛选条件构建。"""
        model_class = model_class or self.model_class
        if not model_class:
            raise HTTPException(status_code=500, detail="model_class is not configured")

        filters = []
        filter_dict = data
        if isinstance(data, BaseModel):
            filter_dict = data.model_dump(mode="json", by_alias=True)
        for key, value in filter_dict.items():
            if include and key in include:
                continue
            if exclude and key in exclude:
                continue
            if not hasattr(model_class, key):
                continue
            if value is None or (not value and value is not False and value != 0):
                continue
            column: Column = getattr(model_class, key)
            if custom_filter:
                custom_filter(filters, column, key, value)
            elif perfect or isinstance(value, bool):
                filters.append(column == value)
            elif isinstance(value, enum.Enum):
                filters.append(column == value.value)
            else:
                filters.append(column.like(f"%{value}%"))
        return filters

    def service_order_by(
        self,
        model_class: Optional[DeclarativeBase] = None,
        order_by: Optional[str] = None,
        sort: Optional[str] = None,
        default_order_by: Optional[str] = None,
        default_sort: Optional[str] = "asc",
        include: Optional[Union[set, dict]] = None,
        exclude: Optional[Union[set, dict]] = None,
        raise_error: bool = True,
    ):
        """业务字段排序。"""
        model_class = model_class or self.model_class
        if not model_class and raise_error:
            raise HTTPException(status_code=500, detail="model_class is not configured")

        order_by = order_by or default_order_by
        sort = sort or default_sort
        if sort != "desc":
            sort = "asc"
        if include and order_by not in include:
            order_by = default_order_by
        elif exclude and order_by in exclude:
            order_by = default_order_by

        if order_by and hasattr(model_class, order_by):
            return getattr(getattr(model_class, order_by), sort)()
        if raise_error:
            raise BadRequestException(detail=f"排序字段 `{order_by}` 不存在")
        if default_order_by and hasattr(model_class, default_order_by):
            return getattr(getattr(model_class, default_order_by), sort)()
        return None
