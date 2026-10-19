import inspect
from collections import defaultdict
from functools import wraps
from typing import Any, overload, Union

_listeners = defaultdict(list)


class Event:
    """
    Event class represents an event with a name and associated data.
    事件类表示具有名称和关联数据的事件。
    """

    def __init__(self, name: str, data: Any):
        """
        Initialize an Event instance.
        初始化事件实例。
        :param name: Event name 事件名称
        :param data: Event data 事件数据
        """
        self.name = name
        self.data = data

    def __repr__(self):
        """
        String representation of the Event.
        事件的字符串表示。
        """
        return f"{self.__class__.__name__}(name={self.name!r}, data={self.data!r})"


class EventManager:
    """
    EventManager handles event registration and triggering.
    事件管理器处理事件注册和触发。
    """

    @staticmethod
    def listen(*event_names: tuple[str]):
        """
        Decorator to register a function as a listener for specified events.
        装饰器，将函数注册为指定事件的监听器。
        :param event_names: Event names to listen for 要监听的事件名称
        :return: Decorated function 装饰后的函数
        """
        def listen_internal(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                return f(*args, **kwargs)

            for event_name in event_names:
                _listeners[event_name].append(f)
            return decorated
        return listen_internal

    @staticmethod
    def listen_for(*event_name: Union[str, tuple[str]]):
        """
        Alias for listen method.
        listen方法的别名。
        :param event_name: Event names to listen for 要监听的事件名称
        :return: Decorated function 装饰后的函数
        """
        return event.listen(*event_name)

    @staticmethod
    @overload
    def emit(event: Event) -> None: ...

    @staticmethod
    @overload
    def emit(event_name: str, data: Any) -> None: ...

    @staticmethod
    def emit(*args, **kwargs):
        """
        Emit an event to all registered listeners.
        向所有注册的监听器发送事件。
        :param args: Positional arguments, either Event object or event_name and data
                    位置参数，可以是Event对象或事件名称和数据
        :param kwargs: Keyword arguments, can include 'event', 'event_name', or 'data'
                      关键字参数，可以包括'event'、'event_name'或'data'
        :raises RuntimeError: If no event parameters are provided 如果未提供事件参数
        """
        if not args and not kwargs.get('event'):
            raise RuntimeError(
                'Missing event trigger parameters. '
                'Either positional arguments or "event" keyword argument must be provided.'
                '触发事件参数不能为空'
            )
        event: Event = kwargs.get('event') or args[0] if isinstance(
            args[0], Event) else None
        if event:
            event_name = event.name
            data = event.data
        else:
            event_name = kwargs.get('event_name') or args[0]
            data = kwargs.get('data') or args[1]

        for listener in _listeners[event_name]:
            parameters = inspect.signature(listener).parameters
            parameters_length = len(parameters)
            if parameters_length == 0:
                listener()
            elif parameters_length == 1:
                listener(data)
            else:
                listener(event_name, data)


# Create a global event manager instance
# 创建全局事件管理器实例
event = EventManager()
