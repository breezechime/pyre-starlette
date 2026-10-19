import logging
import os
import threading
from typing import Any, ClassVar, Optional

import colorlog
from logging import FileHandler, Handler, LogRecord, Formatter

from .config import LoggingConfig
from .constants import LOGGING_NAME, LOGGING_NOTICE

NOTICE = LOGGING_NOTICE
_extensions_ready = False


class PyreLogger(logging.Logger):

    def notice(self, message: object, *args: object, **kwargs: Any) -> None:
        if self.isEnabledFor(NOTICE):
            self._log(NOTICE, message, args, **kwargs)


def get_logger(name: Optional[str] = None) -> PyreLogger:
    global _extensions_ready
    if not _extensions_ready:
        if logging.getLoggerClass() is logging.Logger:
            logging.setLoggerClass(PyreLogger)
        logging.addLevelName(NOTICE, "NOTICE")
        _extensions_ready = True
    return logging.getLogger(name or LOGGING_NAME)  # type: ignore[return-value]


class PyreLogging:

    _instances: ClassVar[dict[str, "PyreLogging"]] = {}

    def __init__(
        self,
        config: Optional[LoggingConfig] = None,
        *,
        sub_logger: bool = False,
    ) -> None:
        self.config = self._resolve_config(config or LoggingConfig(), sub_logger)
        self.logger_name = self.config.name or LOGGING_NAME
        self._attach_to_root = not sub_logger
        self._handlers: list[Handler] = []
        self.child_logger_names: list[str] = []

        previous = PyreLogging._instances.get(self.logger_name)
        if previous is not None and previous is not self:
            previous.shutdown()

        self.thread_log_handler = PyreThreadLogHandler(
            max_entries=self.config.thread_log_max_entries,
            max_chars=self.config.thread_log_max_chars,
        )
        PyreLogging._instances[self.logger_name] = self
        self.logger = self.configure_logger()
        self.init_sub_loggers()

    def reconfigure(self, config: LoggingConfig) -> None:
        """init_app 二次加载时调用：移除旧 handler 后按新配置重建。"""
        self._shutdown_sub_loggers()
        self.shutdown()
        self.config = self._resolve_config(config, sub_logger=False)
        self.logger_name = self.config.name or LOGGING_NAME
        PyreLogging._instances[self.logger_name] = self
        self.thread_log_handler.update_limits(
            self.config.thread_log_max_entries,
            self.config.thread_log_max_chars,
        )
        self.thread_log_handler.clear()
        self.logger = self.configure_logger()
        self.init_sub_loggers()

    def shutdown(self) -> None:
        """移除本实例挂载的 handler 并关闭可释放的资源。"""
        self._shutdown_sub_loggers()
        target = logging.root if self._attach_to_root else logging.getLogger(self.logger_name)
        for handler in list(self._handlers):
            target.removeHandler(handler)
            if handler is not self.thread_log_handler:
                handler.close()
        self._handlers.clear()

    def configure_logger(self) -> PyreLogger:
        logger = get_logger(self.logger_name)
        target = logging.root if self._attach_to_root else logger

        logger.propagate = self._attach_to_root
        logger.setLevel(self.config.level)
        target.setLevel(self.config.level)

        console_formatter = colorlog.ColoredFormatter(
            fmt=self.config.format.console,
            datefmt=self.config.format.dateformat,
            log_colors=self.config.format.log_colors,
        )
        stream_handler = colorlog.StreamHandler()
        stream_handler.setFormatter(console_formatter)
        self._attach_handler(target, stream_handler)

        self.thread_log_handler.setFormatter(
            Formatter(
                fmt=_plain_format(self.config.format.console),
                datefmt=self.config.format.dateformat,
            )
        )
        self._attach_handler(target, self.thread_log_handler)

        if self.config.file_path:
            log_dir = os.path.dirname(os.path.abspath(self.config.file_path))
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            file_handler = FileHandler(self.config.file_path, encoding="utf-8")
            file_handler.setFormatter(
                Formatter(
                    fmt=_plain_format(self.config.format.file),
                    datefmt=self.config.format.dateformat,
                )
            )
            self._attach_handler(target, file_handler)

        return logger

    def _attach_handler(self, logger: logging.Logger, handler: Handler) -> None:
        handler._pyre_logging_handler = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
        self._handlers.append(handler)

    def init_sub_loggers(self) -> None:
        for sub_config in self.config.loggers:
            if not sub_config.name:
                continue
            if sub_config.name == self.logger_name:
                continue
            child = PyreLogging(sub_config, sub_logger=True)
            self.child_logger_names.append(child.logger_name)

    @staticmethod
    def _resolve_config(config: LoggingConfig, sub_logger: bool) -> LoggingConfig:
        """将与主 logger 同名的子配置合并到主配置，避免 shutdown 掉 root handler。"""
        if sub_logger:
            return config
        main_name = config.name or LOGGING_NAME
        sub_loggers: list[LoggingConfig] = []
        merged = config
        for sub in config.loggers:
            if sub.name == main_name:
                merged = PyreLogging._merge_logging_config(merged, sub)
            else:
                sub_loggers.append(sub)
        if sub_loggers is not config.loggers:
            merged = merged.model_copy(update={'loggers': sub_loggers})
        return merged

    @staticmethod
    def _merge_logging_config(base: LoggingConfig, override: LoggingConfig) -> LoggingConfig:
        updates = override.model_dump(exclude_unset=True, exclude={'name', 'loggers'})
        if 'format' in updates:
            updates['format'] = base.format.model_copy(
                update=override.format.model_dump(exclude_unset=True)
            )
        return base.model_copy(update=updates)

    def _shutdown_sub_loggers(self) -> None:
        for name in self.child_logger_names:
            child = PyreLogging._instances.pop(name, None)
            if child is not None:
                child.shutdown()
        self.child_logger_names.clear()


class PyreThreadLogHandler(Handler):

    def __init__(
        self,
        max_entries: int = 500,
        max_chars: int = 65536,
    ) -> None:
        super().__init__()
        self.max_entries = max(1, max_entries)
        self.max_chars = max(1024, max_chars)
        self.local = threading.local()
        self.formatter = Formatter()

    def get_log_data(self) -> str:
        return "\n".join(self._get_logs(create=False))

    def update_limits(self, max_entries: int, max_chars: int) -> None:
        self.max_entries = max(1, max_entries)
        self.max_chars = max(1024, max_chars)
        self._trim(self._get_logs(create=False))

    def emit(self, record: LogRecord) -> None:
        if threading.main_thread().ident == threading.get_ident():
            return
        self.add_log_message(self.formatter.format(record))

    def add_log_message(self, message: str) -> None:
        logs = self._get_logs(create=True)
        logs.append(message)
        self._trim(logs)

    def _get_logs(self, create: bool) -> list[str]:
        logs = getattr(self.local, "thread_log", None)
        if logs is None:
            if not create:
                return []
            logs = []
            self.local.thread_log = logs
        return logs

    def _trim(self, logs: list[str]) -> None:
        while len(logs) > self.max_entries:
            logs.pop(0)
        while logs and self._total_chars(logs) > self.max_chars:
            logs.pop(0)

    @staticmethod
    def _total_chars(logs: list[str]) -> int:
        if not logs:
            return 0
        return sum(len(item) for item in logs) + len(logs) - 1

    def clear(self) -> None:
        if hasattr(self.local, "thread_log"):
            self.local.thread_log = []


def _plain_format(fmt: str) -> str:
    """去掉仅 ColoredFormatter 支持的 %(log_color)s。"""
    return fmt.replace('%(log_color)s', '')