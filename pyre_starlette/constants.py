import enum
from typing import Any, Union, TypeVar, Callable

ART_TEXT = r"""
 ____                 ____  _             _      _   _       
|  _ \ _   _ _ __ ___/ ___|| |_ __ _ _ __| | ___| |_| |_ ___ 
| |_) | | | | '__/ _ \___ \| __/ _` | '__| |/ _ \ __| __/ _ |
|  __/| |_| | | |  __/___) | || (_| | |  | |  __/ |_| ||  __/
|_|    \__, |_|  \___|____/ \__\__,_|_|  |_|\___|\__|\__\___|
       |___/                                                 
"""

# 日志默认格式化
LOGGING_NAME = 'pyre_starlette'
LOGGING_NOTICE = 28
LOGGING_PLAIN_FORMAT = '%(asctime)s %(filename)s:%(lineno)d [%(levelname)s] %(message)s'
LOGGING_FORMAT = '%(log_color)s' + LOGGING_PLAIN_FORMAT


# 日志颜色
LOG_COLORS = {
    'DEBUG': 'white',
    'INFO': 'green',
    'NOTICE': 'cyan',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'bold_red',
}

_T = TypeVar("_T", bound="Any")
PrimaryKey = Union[str, int]
Class = TypeVar("Class", type, object, Callable)


class GeneralStatus(enum.IntEnum):
    """通用状态枚举"""

    """禁用"""
    DISABLED = 0

    """正常"""
    NORMAL = 1