from typing import Optional
import re
import warnings
from starlette.requests import Request

DEFAULT_LOCALE = "zh-hans"


LOCALE_MESSAGES: dict[str, dict[str, str]] = {
    "zh-hans": {
        "Not Found": "请求的地址不存在，可能已被删除或刷新重试",
        "Not Found Data": "未找到数据，可能已被删除",
        "Request Parameter Error": "请求参数错误",
        "Request Validation Error": "请求参数校验错误",
        "Unauthorized": "请先登录后再操作",
        "Forbidden": "暂无权限操作",
        "Method Not Allowed": "该方法不允许此方式请求",
        "The server does not support the media type transmitted in the request": "无法解析请求中不支持的媒体类型",
        "Authentication Timeout": "身份信息过期，请重新登录",
        "Internal Server Error": "服务发生意外错误, 请稍后重试!",
        "Field": "字段",
    },
    "en": {},
}

# 业务层可覆盖的自定义文案（通过 register_messages 注册）
_CUSTOM_LOCALE_MESSAGES: dict[str, dict[str, str]] = {}
_CUSTOM_VALIDATION_TYPE_MESSAGES: dict[str, dict[str, str]] = {}
_CUSTOM_VALIDATION_MSG_MESSAGES: dict[str, dict[str, str]] = {}

# Pydantic validation: prefer error type
LOCALE_VALIDATION_TYPE_MESSAGES: dict[str, dict[str, str]] = {
    "zh-hans": {
        "missing": "必填项",
        "int_parsing": "输入应为有效整数",
        "float_parsing": "输入应为有效数字",
        "bool_parsing": "输入应该是有效的布尔值",
        "string_type": "输入应为有效字符串",
        "dict_type": "输入应该是有效的键值对",
        "model_type": "输入应该是有效的对象",
    },
    "en": {
        "missing": "Field required",
        "int_parsing": "Input should be a valid integer",
        "float_parsing": "Input should be a valid number",
        "bool_parsing": "Input should be a valid boolean",
        "string_type": "Input should be a valid string",
        "dict_type": "Input should be a valid dictionary",
        "model_type": "Input should be a valid object",
    },
}

# Pydantic validation: fallback by English msg (from pyre_flask)
LOCALE_VALIDATION_MSG_MESSAGES: dict[str, dict[str, str]] = {
    "zh-hans": {
        "Field required": "必填项",
        "Input should be a valid integer": "输入应为有效整数",
        "Input should be a valid integer, unable to parse string as an integer": "输入应为有效整数，无法将字符串解析为整数",
        "Input should be a valid boolean": "输入应该是有效的布尔值",
        "Input should be a valid string": "输入应为有效字符串",
        "Datetimes provided to dates should have zero time - e.g. be exact dates": "输入应为e.g. 2021-01-01 日期类型",
        "Input should be a valid dictionary": "输入应该是有效的键值对",
        "Input should be a valid dictionary or object to extract fields from": "输入应该是有效的字典或对象以从中提取字段",
    },
    "en": {},
}


# Pydantic 动态 msg 可能携带后端类名，用 pattern 替换为通用文案
_SANITIZE_VALIDATION_MSG_PATTERNS: list[tuple[re.Pattern[str], dict[str, str]]] = [
    (
        re.compile(r"^Input should be a valid dictionary or instance of .+$"),
        {"zh-hans": "输入应该是有效的对象", "en": "Input should be a valid object"},
    ),
    (
        re.compile(r"^Input should be an instance of .+$"),
        {"zh-hans": "输入应该是有效的对象", "en": "Input should be a valid object"},
    ),
    (
        re.compile(r"^Input should be a valid .+ or instance of .+$"),
        {"zh-hans": "输入格式不正确", "en": "Invalid input format"},
    ),
]


def _normalize_locale(locale: str) -> str:
    if locale.startswith("zh"):
        return "zh-hans"
    return "en"


def register_messages(locale: str, messages: dict[str, str]) -> None:
    """Register or override locale messages from business layer."""
    lang = _normalize_locale(locale)
    _CUSTOM_LOCALE_MESSAGES.setdefault(lang, {}).update(messages)


def register_validation_type_messages(locale: str, messages: dict[str, str]) -> None:
    """Register or override pydantic error type messages."""
    lang = _normalize_locale(locale)
    _CUSTOM_VALIDATION_TYPE_MESSAGES.setdefault(lang, {}).update(messages)


def register_validation_msg_messages(locale: str, messages: dict[str, str]) -> None:
    """Register or override pydantic error msg messages."""
    lang = _normalize_locale(locale)
    _CUSTOM_VALIDATION_MSG_MESSAGES.setdefault(lang, {}).update(messages)


def resolve_locale(request: Optional[Request] = None) -> str:
    """Resolve locale from request app config, or use default."""
    if request is not None:
        app = request.app
        app_config = getattr(app, "app_config", None)
        if app_config is not None:
            return getattr(app_config.pyre, "locale", DEFAULT_LOCALE)

    try:
        from ..requests import try_get_request

        ctx_request = try_get_request()
        if ctx_request is not None:
            return resolve_locale(ctx_request)
    except Exception as e:
        warnings.warn(f"Exception occurred while resolving locale: {e}")
    return DEFAULT_LOCALE


def get_message(
    key: str,
    locale: Optional[str] = None,
) -> str:
    """Get message by key; custom registered messages take priority."""
    locale = locale or resolve_locale()
    lang = _normalize_locale(locale)

    custom = _CUSTOM_LOCALE_MESSAGES.get(lang, {}).get(key)
    if custom is not None:
        return custom

    msg = LOCALE_MESSAGES.get(lang, {}).get(key)
    if msg is not None:
        return msg

    if lang != "en":
        custom = _CUSTOM_LOCALE_MESSAGES.get("en", {}).get(key)
        if custom is not None:
            return custom
        msg = LOCALE_MESSAGES.get("en", {}).get(key)
        if msg is not None:
            return msg

    return key


def _sanitize_validation_msg(msg: str, locale: str) -> str:
    """Remove internal class names leaked by pydantic dynamic error messages."""
    lang = _normalize_locale(locale)
    for pattern, replacements in _SANITIZE_VALIDATION_MSG_PATTERNS:
        if pattern.match(msg):
            return replacements.get(lang, replacements.get("en", msg))
    stripped = re.sub(r" or instance of [\w\.\[\]]+$", "", msg)
    if stripped != msg:
        if lang == "zh-hans":
            return "输入应该是有效的对象"
        return stripped
    return msg


def translate_validation_msg(
    msg: str,
    error_type: str = "",
    locale: Optional[str] = None,
) -> str:
    """Translate a single pydantic validation error message."""
    locale = locale or resolve_locale()
    lang = _normalize_locale(locale)

    for source in (_CUSTOM_VALIDATION_TYPE_MESSAGES, LOCALE_VALIDATION_TYPE_MESSAGES):
        type_msg = source.get(lang, {}).get(error_type)
        if type_msg:
            return type_msg
    type_msg = LOCALE_VALIDATION_TYPE_MESSAGES.get("en", {}).get(error_type)
    if type_msg:
        return type_msg

    for source in (_CUSTOM_VALIDATION_MSG_MESSAGES, LOCALE_VALIDATION_MSG_MESSAGES):
        if lang == "zh-hans":
            translated = source.get("zh-hans", {}).get(msg)
            if translated:
                return translated

    sanitized = _sanitize_validation_msg(msg, locale)
    if sanitized != msg:
        return sanitized

    if lang == "zh-hans":
        return (
            msg.replace("String should have at most ", "字符串最多应包含")
            .replace(" characters", "个字符")
        )
    return msg
