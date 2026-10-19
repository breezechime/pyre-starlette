"""Logging: notice level, thread log handler and ``PyreLogging`` lifecycle."""
import logging
import threading

import pytest

from pyre_starlette.config import LoggingConfig, LoggingFormaterConfig
from pyre_starlette.logger import (
    PyreLogger,
    PyreLogging,
    PyreThreadLogHandler,
    _plain_format,
    get_logger,
)
from pyre_starlette.constants import LOGGING_NAME, LOGGING_NOTICE


@pytest.fixture(autouse=True)
def _restore_logging_state():
    """``PyreLogging`` touches the global root logger; restore it after each test."""
    instances = dict(PyreLogging._instances)
    handlers = list(logging.root.handlers)
    level = logging.root.level
    try:
        yield
    finally:
        PyreLogging._instances.clear()
        PyreLogging._instances.update(instances)
        logging.root.handlers[:] = handlers
        logging.root.setLevel(level)


def _record(message="msg", level=logging.INFO):
    return logging.LogRecord("pyre-test", level, __file__, 1, message, None, None)


# --------------------------------------------------------------------------- #
# level / logger class
# --------------------------------------------------------------------------- #

def test_notice_level_is_registered():
    get_logger("pyre-test-notice-level")
    assert logging.getLevelName(LOGGING_NOTICE) == "NOTICE"


def test_get_logger_returns_pyre_logger_with_notice():
    logger = get_logger("pyre-test-notice-method")
    assert logging.getLoggerClass() is PyreLogger
    assert isinstance(logger, PyreLogger)
    assert logger.name == "pyre-test-notice-method"


def test_get_logger_defaults_to_package_name():
    assert get_logger().name == LOGGING_NAME


def test_notice_method_emits_at_notice_level(caplog):
    logger = get_logger("pyre-test-emit")
    logger.setLevel(LOGGING_NOTICE)
    with caplog.at_level(LOGGING_NOTICE, logger="pyre-test-emit"):
        logger.notice("hello %s", "world")
    assert "hello world" in caplog.text
    assert caplog.records[-1].levelno == LOGGING_NOTICE


def test_notice_method_is_suppressed_below_level():
    logger = get_logger("pyre-test-suppress")
    logger.setLevel(logging.WARNING)

    seen = []

    class _Collect(logging.Handler):
        def emit(self, record):
            seen.append(record)

    handler = _Collect()
    logger.addHandler(handler)
    try:
        logger.notice("nope")
    finally:
        logger.removeHandler(handler)

    assert seen == []


# --------------------------------------------------------------------------- #
# thread log handler
# --------------------------------------------------------------------------- #

def test_thread_log_handler_ignores_main_thread():
    handler = PyreThreadLogHandler()
    handler.emit(_record("from-main"))
    assert handler.get_log_data() == ""


def test_thread_log_handler_captures_worker_thread():
    handler = PyreThreadLogHandler()
    record = _record("worker-line")
    captured = {}

    def run():
        handler.emit(record)
        captured["data"] = handler.get_log_data()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    assert "worker-line" in captured["data"]


def test_thread_log_handler_trim_by_entries():
    handler = PyreThreadLogHandler(max_entries=3)
    for i in range(5):
        handler.add_log_message(f"m{i}")
    assert handler.get_log_data().splitlines() == ["m2", "m3", "m4"]


def test_thread_log_handler_trim_by_chars():
    handler = PyreThreadLogHandler(max_entries=1000, max_chars=1024)
    for i in range(40):
        handler.add_log_message(f"{i:03d}" + "x" * 97)  # 100 chars each
    lines = handler.get_log_data().splitlines()
    assert 0 < len(lines) < 40
    assert lines[-1].startswith("039")
    assert not any(line.startswith("000") for line in lines)


def test_thread_log_handler_update_limits_trims_and_clamps():
    handler = PyreThreadLogHandler()
    for i in range(10):
        handler.add_log_message(f"m{i}")
    handler.update_limits(2, 1024)
    assert handler.get_log_data().splitlines() == ["m8", "m9"]

    handler.update_limits(0, 0)  # clamped to sane minimums
    assert handler.max_entries == 1
    assert handler.max_chars == 1024


def test_thread_log_handler_clear():
    handler = PyreThreadLogHandler()
    handler.add_log_message("x")
    handler.clear()
    assert handler.get_log_data() == ""


def test_plain_format_strips_color_placeholder():
    assert _plain_format("%(log_color)s%(message)s") == "%(message)s"
    assert _plain_format("%(message)s") == "%(message)s"


# --------------------------------------------------------------------------- #
# PyreLogging lifecycle
# --------------------------------------------------------------------------- #

def test_pyre_logging_attaches_and_shutdowns_handlers():
    logging_instance = PyreLogging(LoggingConfig(name="pyre-test-life", level=logging.INFO))
    try:
        assert logging_instance.logger.name == "pyre-test-life"
        assert logging_instance.thread_log_handler in logging.root.handlers
        assert PyreLogging._instances["pyre-test-life"] is logging_instance
    finally:
        logging_instance.shutdown()

    assert logging_instance.thread_log_handler not in logging.root.handlers
    assert logging_instance._handlers == []


def test_pyre_logging_writes_to_file(tmp_path):
    log_file = tmp_path / "nested" / "app.log"
    logging_instance = PyreLogging(
        LoggingConfig(name="pyre-test-file", level=logging.INFO, file_path=str(log_file))
    )
    try:
        logging_instance.logger.error("boom")
    finally:
        logging_instance.shutdown()

    assert log_file.exists()
    assert "boom" in log_file.read_text(encoding="utf-8")


def test_reconfigure_rebuilds_handlers():
    logging_instance = PyreLogging(LoggingConfig(name="pyre-test-reconf", level=logging.INFO))
    try:
        logging_instance.reconfigure(LoggingConfig(name="pyre-test-reconf", level=logging.DEBUG))
        assert logging_instance.config.level == logging.DEBUG
        assert logging_instance._handlers
        assert logging_instance.logger.level == logging.DEBUG
    finally:
        logging_instance.shutdown()


def test_same_name_child_config_is_merged_into_main():
    config = LoggingConfig(
        name="pyre-test-merge",
        level=logging.INFO,
        loggers=[LoggingConfig(name="pyre-test-merge", level=logging.ERROR)],
    )
    logging_instance = PyreLogging(config)
    try:
        assert logging_instance.config.level == logging.ERROR
        assert logging_instance.config.loggers == []
        assert logging_instance.child_logger_names == []
    finally:
        logging_instance.shutdown()


def test_sub_loggers_are_created_and_cleaned():
    config = LoggingConfig(
        name="pyre-test-main",
        loggers=[LoggingConfig(name="pyre-test-child", level=logging.INFO)],
    )
    logging_instance = PyreLogging(config)
    try:
        assert "pyre-test-child" in logging_instance.child_logger_names
        assert "pyre-test-child" in PyreLogging._instances
    finally:
        logging_instance.shutdown()

    assert "pyre-test-child" not in PyreLogging._instances


def test_merge_logging_config_keeps_base_format_defaults():
    base = LoggingConfig(name="pyre-test-fmt")
    override = LoggingConfig(name="pyre-test-fmt", format=LoggingFormaterConfig(dateformat="%H:%M"))
    merged = PyreLogging._merge_logging_config(base, override)
    assert merged.format.dateformat == "%H:%M"
    assert merged.format.console == base.format.console


def test_replacing_instance_with_same_name_shuts_previous_down():
    first = PyreLogging(LoggingConfig(name="pyre-test-swap", level=logging.INFO))
    first_handler = first.thread_log_handler
    second = PyreLogging(LoggingConfig(name="pyre-test-swap", level=logging.INFO))
    try:
        assert first_handler not in logging.root.handlers
        assert second.thread_log_handler in logging.root.handlers
    finally:
        second.shutdown()


def test_app_exposes_pyre_logger_and_thread_handler(app):
    assert isinstance(app.logging, PyreLogging)
    assert app.logger is app.logging.logger
    assert isinstance(app.logging.thread_log_handler, PyreThreadLogHandler)


def test_notice_flag_controls_startup_log(caplog):
    """``notice=False`` must silence the startup notice."""
    from pyre_starlette import PyreStarlette

    def build(notice):
        caplog.set_level(LOGGING_NOTICE, logger=LOGGING_NAME)
        caplog.clear()
        PyreStarlette(notice=notice)
        return [r for r in caplog.records if r.levelno == LOGGING_NOTICE]

    assert build(notice=False) == []
    assert len(build(notice=True)) == 2

