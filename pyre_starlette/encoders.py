import dataclasses
import datetime
import decimal
import functools
import json.encoder
import uuid
from collections import deque
from contextvars import ContextVar
from enum import Enum
from ipaddress import (
    IPv4Address,
    IPv4Interface,
    IPv4Network,
    IPv6Address,
    IPv6Interface,
    IPv6Network,
)
from pathlib import PurePath, Path
from re import Pattern
from types import GeneratorType
from typing import Any, Optional, Dict, Callable, List

try:
    from flask.json.provider import DefaultJSONProvider
except ImportError:  # Flask 为可选依赖
    DefaultJSONProvider = None

from pydantic import BaseModel
from pydantic.main import IncEx
from pydantic.networks import AnyUrl, NameEmail
from pydantic.types import SecretBytes, SecretStr
from pydantic_core import PydanticSerializationError
from sqlalchemy import Row

_serialize_seen: ContextVar[Optional[set]] = ContextVar("pyre_jsonable_encoder_seen", default=None)

BASE_TYPE_ENCODERS = {
    bytes: lambda o: o.decode(),
    datetime.timedelta: lambda td: td.total_seconds(),
    frozenset: lambda o: list(o),
    deque: lambda o: list(o),
    GeneratorType: lambda o: list(o),
    IPv4Address: lambda o: str(o),
    IPv4Interface: lambda o: str(o),
    IPv4Network: lambda o: str(o),
    IPv6Address: lambda o: str(o),
    IPv6Interface: lambda o: str(o),
    IPv6Network: lambda o: str(o),
    NameEmail: lambda o: str(o),
    Path: lambda o: str(o),
    Pattern: lambda o: o.pattern,
    SecretBytes: lambda o: str(o),
    SecretStr: lambda o: str(o),
    set: lambda o: list(o),
    AnyUrl: lambda o: str(o),
}


def break_recursion_serialize(func):
    """
    防止序列化函数在处理循环引用时无限递归。

    以 ``ContextVar`` 保存当前调用路径，线程与异步任务之间互不干扰。
    """

    @functools.wraps(func)
    def wrapper(obj: Any, *args, **kwargs) -> Any:
        seen = _serialize_seen.get()
        is_root = seen is None
        if is_root:
            seen = set()
            token = _serialize_seen.set(seen)

        obj_id = id(obj)
        if obj_id in seen:
            return None
        seen.add(obj_id)
        try:
            return func(obj, *args, **kwargs)
        finally:
            seen.discard(obj_id)
            if is_root:
                _serialize_seen.reset(token)

    return wrapper


@break_recursion_serialize
def jsonable_encoder(
    obj: Any,
    include: Optional[IncEx] = None,
    exclude: Optional[IncEx] = None,
    by_alias: bool = True,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    exclude_none: bool = False,
    custom_encoder: Optional[Dict[Any, Callable[[Any], Any]]] = None,
    sqlalchemy_safe: bool = True,
) -> Any:
    custom_encoder = custom_encoder or {}
    obj_type = type(obj)
    if obj_type in custom_encoder:
        return custom_encoder[obj_type](obj)
    else:
        for encoder_type, encoder_instance in custom_encoder.items():
            if isinstance(obj, encoder_type):
                return encoder_instance(obj)

    if include is not None and not isinstance(include, (set, dict)):
        include = set(include)
    if exclude is not None and not isinstance(exclude, (set, dict)):
        exclude = set(exclude)

    if isinstance(obj, BaseModel):
        # pydantic 模型
        try:
            obj_dict = obj.model_dump(
                mode="json",
                include=include,
                exclude=exclude,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_none=exclude_none,
                exclude_defaults=exclude_defaults,
            )
        except PydanticSerializationError:
            obj_dict = obj.model_dump(
                mode="python",
                include=include,
                exclude=exclude,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_none=exclude_none,
                exclude_defaults=exclude_defaults,
            )
        if "__root__" in obj_dict:
            obj_dict = obj_dict["__root__"]
        return jsonable_encoder(
            obj_dict,
            exclude=exclude,
            include=include,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_none=exclude_none,
            exclude_defaults=exclude_defaults,
            custom_encoder=custom_encoder,
            sqlalchemy_safe=sqlalchemy_safe,
        )
    elif isinstance(obj, (str, int, float, type(None))):
        return obj
    elif isinstance(obj, (decimal.Decimal, uuid.UUID, PurePath)):
        return str(obj)
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, datetime.datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(obj, (datetime.date, datetime.time)):
        return obj.isoformat()
    elif dataclasses.is_dataclass(obj):
        obj_dict = dataclasses.asdict(obj)
        return jsonable_encoder(
            obj_dict,
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            custom_encoder=custom_encoder,
            sqlalchemy_safe=sqlalchemy_safe,
        )
    elif isinstance(obj, Row):
        obj = obj._asdict()
    if isinstance(obj, dict):
        encoded_dict = {}
        allowed_keys = set(obj.keys())
        if include is not None:
            allowed_keys &= set(include)
        if exclude is not None:
            allowed_keys -= set(exclude)
        for key, value in obj.items():
            if (
                    (
                        not sqlalchemy_safe
                        or (not isinstance(key, str))
                        or (not key.startswith("_sa"))
                    )
                    and (value is not None or not exclude_none)
                    and key in allowed_keys
            ):
                encoded_key = jsonable_encoder(
                    key,
                    by_alias=by_alias,
                    exclude_unset=exclude_unset,
                    exclude_none=exclude_none,
                    custom_encoder=custom_encoder,
                    sqlalchemy_safe=sqlalchemy_safe,
                )
                encoded_value = jsonable_encoder(
                    value,
                    by_alias=by_alias,
                    exclude_unset=exclude_unset,
                    exclude_none=exclude_none,
                    custom_encoder=custom_encoder,
                    sqlalchemy_safe=sqlalchemy_safe,
                )
                encoded_dict[encoded_key] = encoded_value
        return encoded_dict
    if isinstance(obj, (list, set, frozenset, GeneratorType, tuple, deque)):
        encoded_list = []
        for item in obj:
            encoded_list.append(
                jsonable_encoder(
                    item,
                    include=include,
                    exclude=exclude,
                    by_alias=by_alias,
                    exclude_unset=exclude_unset,
                    exclude_defaults=exclude_defaults,
                    exclude_none=exclude_none,
                    custom_encoder=custom_encoder,
                    sqlalchemy_safe=sqlalchemy_safe,
                )
            )
        return encoded_list

    # base type encoders 基础类型编码器
    if obj_type in BASE_TYPE_ENCODERS:
        return BASE_TYPE_ENCODERS[obj_type](obj)

    try:
        data = dict(obj)
    except Exception as e:
        errors: List[Exception] = [e]
        try:
            data = vars(obj)
        except Exception as e:
            errors.append(e)
            raise ValueError(errors) from e

    return jsonable_encoder(
        data,
        include=include,
        exclude=exclude,
        by_alias=by_alias,
        exclude_unset=exclude_unset,
        exclude_none=exclude_none,
        exclude_defaults=exclude_defaults,
        custom_encoder=custom_encoder,
        sqlalchemy_safe=sqlalchemy_safe,
    )


def _default(o: Any):
    if hasattr(o, 'model_dump'):
        # 注意options为动态属性，不建议修改
        return o.model_dump(mode='json', **getattr(o, '_options', {}), fallback=_default)
    try:
        return jsonable_encoder(o)
    except Exception:
        raise TypeError(f'Object of type {o.__class__.__name__} is not JSON serializable')


class PyreJSONEncoder(json.encoder.JSONEncoder):
    ensure_ascii = False

    def default(self, o):
        return _default(o)


if DefaultJSONProvider is not None:

    class PyreJSONProvider(DefaultJSONProvider):
        """自定义的 Flask JSON 编码器"""
        ensure_ascii = False

        default = staticmethod(_default)

else:

    class PyreJSONProvider:  # type: ignore[no-redef]
        """Flask 未安装时的占位实现。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("PyreJSONProvider 需要安装 flask 后使用")

