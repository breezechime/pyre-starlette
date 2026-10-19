from enum import Enum
from inspect import _empty
from typing import Annotated, Any, Literal, Optional, Unpack, get_args, get_origin

from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo, _FromFieldInfoInputs
from pydantic_core import PydanticUndefined

from .exceptions.exceptions import RequestValidationError


def resolve_model_input(values: dict[str, Any], key: str) -> Any:
    """
    Pick input for a BaseModel parameter.

    Supports nested key (``?user={"name": "a"}`` dict) or flat fields (``?name=a&age=1``).
    """
    if key in values:
        return values[key]
    return values


def validate_model_param(
    model_cls: type[BaseModel],
    values: dict[str, Any],
    *,
    key: Optional[str] = None,
) -> BaseModel:
    """Validate and construct a BaseModel parameter; raise RequestValidationError on failure."""
    raw = resolve_model_input(values, key or "")
    if isinstance(raw, model_cls):
        return raw
    if raw is None:
        raw = {}
    if not isinstance(raw, (dict, list, str, int, float, bool)):
        raise_model_type_validation_error(key, raw)
    try:
        return model_cls.model_validate(raw)
    except ValidationError as error:
        exc = RequestValidationError.from_exception_data(
            title=error.title,
            line_errors=error.errors(),
        )
        exc.key = key  # type: ignore[attr-defined]
        raise exc
    except TypeError:
        raise_model_type_validation_error(key, raw)


def raise_model_type_validation_error(
    key: Optional[str],
    value: Any,
    *,
    msg: str = "Input should be a valid dictionary or object",
) -> None:
    """Raise RequestValidationError when model input is not a mapping."""
    loc = (key,) if key else ("body",)
    exc = RequestValidationError.from_exception_data(
        title="Validation Error",
        line_errors=[{
            "type": "model_type",
            "loc": loc,
            "msg": msg,
            "input": value,
        }],
    )
    exc.key = key  # type: ignore[attr-defined]
    raise exc
    

class ParamTypes(str, Enum):
    query = "query"
    path = "path"
    header = "header"
    cookie = "cookie"
    body = "body"


class ParamInfo(FieldInfo):
    """参数元数据基类，标记参数来源（供 OpenAPI 生成使用）。"""

    in_: ParamTypes | None = None

    @classmethod
    def from_field(
        cls,
        default: Any = PydanticUndefined,
        *,
        in_: ParamTypes | None = None,
        **kwargs: Unpack[_FromFieldInfoInputs],
    ) -> "ParamInfo":
        if "annotation" in kwargs:
            raise TypeError('"annotation" is not permitted as a Field keyword argument')
        return cls(default=default, in_=in_, **kwargs)


class QueryInfo(ParamInfo):
    in_: Literal[ParamTypes.query] = ParamTypes.query


class BodyInfo(ParamInfo):
    in_: Literal[ParamTypes.body] = ParamTypes.body
    embed: bool | None = None
    media_type: str = "application/json"


class PathInfo(ParamInfo):
    in_: Literal[ParamTypes.path] = ParamTypes.path


class HeaderInfo(ParamInfo):
    in_: Literal[ParamTypes.header] = ParamTypes.header
    convert_underscores: bool = True


class CookieInfo(ParamInfo):
    in_: Literal[ParamTypes.cookie] = ParamTypes.cookie


def resolve_annotated_param(annotation: Any) -> tuple[Any, ParamInfo | None]:
    """解析 Annotated[T, ParamInfo] 形式的参数注解。"""
    if annotation is _empty:
        return Any, None
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        if not args:
            return Any, None
        inner = args[0]
        for item in args[1:]:
            if isinstance(item, ParamInfo):
                return inner, item
        return inner, None
    return annotation, None


def validate_param_value(annotation: Any, value: Any, key: Optional[str] = None, by_alias: bool = True) -> Any:
    """按 Annotated[T, ParamInfo] 或裸类型校验单个参数值。"""
    if annotation is _empty:
        return value
    try:
        return TypeAdapter(annotation).validate_python(value, by_alias=by_alias)
    except ValidationError as e:
        exc = RequestValidationError.from_exception_data(
            title=e.title,
            line_errors=e.errors(),
        )
        exc.key = key  # type: ignore[attr-defined]
        raise exc


def header_lookup_key(name: str, meta: HeaderInfo) -> str:
    alias = getattr(meta, "alias", None)
    if isinstance(alias, str) and alias:
        return alias
    if meta.convert_underscores:
        return name.replace("_", "-")
    return name


def Query(*args: Any, **kwargs: Any) -> QueryInfo:
    return QueryInfo.from_field(*args, in_=ParamTypes.query, **kwargs)


def Body(
    *args: Any,
    embed: bool | None = None,
    media_type: str = "application/json",
    **kwargs: Any,
) -> BodyInfo:
    field_info = BodyInfo.from_field(*args, in_=ParamTypes.body, **kwargs)
    field_info.embed = embed
    field_info.media_type = media_type
    return field_info


def Path(*args: Any, **kwargs: Any) -> PathInfo:
    return PathInfo.from_field(*args, in_=ParamTypes.path, **kwargs)


def Header(
    *args: Any,
    convert_underscores: bool = True,
    **kwargs: Any,
) -> HeaderInfo:
    field_info = HeaderInfo.from_field(*args, in_=ParamTypes.header, **kwargs)
    field_info.convert_underscores = convert_underscores
    return field_info


def Cookie(*args: Any, **kwargs: Any) -> CookieInfo:
    return CookieInfo.from_field(*args, in_=ParamTypes.cookie, **kwargs)
