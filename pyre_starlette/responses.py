from typing import Any, TypeVar
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError

from starlette.background import BackgroundTask, BackgroundTasks  # noqa: F401
from starlette.responses import Response  # noqa: F401
from starlette.responses import JSONResponse  # noqa: F401
from starlette.responses import FileResponse  # noqa: F401
from starlette.responses import HTMLResponse  # noqa: F401
from starlette.responses import PlainTextResponse  # noqa: F401
from starlette.responses import RedirectResponse  # noqa: F401
from starlette.responses import StreamingResponse  # noqa: F401

from .encoders import jsonable_encoder  # noqa: F401

DataT = TypeVar('DataT', bound=Any)


def build_response(
    response: Any, 
    status_code: int = 200,
    exclude: Any = None,
    include: Any = None,
    exclude_none: bool = False,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    by_alias: bool = True,
    validate_response_model: bool = True,
    response_model: Any = None,
) -> Response:
    """Serialize endpoint response into an HTTP response. 
    将 endpoint 返回值序列化为 HTTP 响应
    """
    
    # is raw response
    if isinstance(response, Response):
        return response

    # validate response model
    if (
        validate_response_model
        and response_model
        and (not status_code or status_code == 200)
    ):
        is_basemodel = isinstance(response_model, type) and issubclass(response_model, BaseModel)
        adapter = TypeAdapter(response_model) if not is_basemodel else None

        try:
            # 快速路径：纯 pydantic 对象直接验证，from_attributes 处理同结构类型转换
            if is_basemodel:
                response = response_model.model_validate(response, from_attributes=True)
            else:
                response = adapter.validate_python(response, from_attributes=True)
        except ValidationError:
            # 慢速路径：response 中嵌套了非 pydantic 对象（如 SQLAlchemy Model），
            # from_attributes 无法递归处理，先转成纯 dict 再验证
            raw = response.model_dump(mode="python") if isinstance(response, BaseModel) else response
            encoded = jsonable_encoder(raw)
            if is_basemodel:
                response = response_model.model_validate(encoded)
            else:
                response = adapter.validate_python(encoded)

    # serialize response
    if isinstance(response, BaseModel):
        try:
            content = response.model_dump(
                mode="json",
                exclude=exclude,
                include=include,
                exclude_none=exclude_none,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                by_alias=by_alias
            )
        except PydanticSerializationError:
            content = jsonable_encoder(
                response,
                exclude=exclude,
                include=include,
                exclude_none=exclude_none,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                by_alias=by_alias,
            )
        json_response = JSONResponse(content, status_code=status_code)
    else:
        json_response = JSONResponse(jsonable_encoder(response), status_code=status_code)

    # 检测 ResultResponse 上携带的后台任务，附加到 JSONResponse
    bg = getattr(response, '_background', None)
    if bg:
        json_response.background = bg

    return json_response


def common_response(
    code: int = 200,
    msg: str = 'success',
    **kwargs
):
    """common response"""
    return jsonable_encoder(dict(code=code, msg=msg, **kwargs))
