import uuid
from inspect import _empty
from typing import Annotated, Any

from pydantic import Field, TypeAdapter
from starlette.convertors import (
    Convertor,
    FloatConvertor,
    IntegerConvertor,
    PathConvertor,
    UUIDConvertor,
)


def parse_convertor_schema(convertor: Convertor) -> dict[str, Any]:
    """将 Starlette 路径转换器映射为 OpenAPI schema。"""
    if isinstance(convertor, IntegerConvertor):
        annotation = int
        json_schema_extra = {"format": "int32"}
    elif isinstance(convertor, FloatConvertor):
        annotation = float
        json_schema_extra = {"format": "float"}
    elif isinstance(convertor, UUIDConvertor):
        annotation = uuid.UUID
        json_schema_extra = {"format": "uuid"}
    elif isinstance(convertor, PathConvertor):
        annotation = str
        json_schema_extra = {"format": "path"}
    else:
        annotation = str
        json_schema_extra = {}

    return TypeAdapter(
        Annotated[annotation, Field(json_schema_extra=json_schema_extra)]
    ).json_schema()


def path_param_required(func_param: Any) -> bool:
    """路径参数默认必填；显式 default 时按签名判断。"""
    if func_param is None:
        return True
    return getattr(func_param, "default", _empty) is _empty
