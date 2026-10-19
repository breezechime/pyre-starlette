"""Shared fixtures for the pyre-starlette test suite.

The library depends on ``pyre-config``, ``pyre-injector`` and ``sqlalchemy-db``.
When those are not installed the sibling source directories of this repository are
put on ``sys.path`` so the suite runs straight from a checkout.
"""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_LIB_ROOT)

for _name in ("pyre-injector", "pyre-config", "sqlalchemy-db", "pyre-starlette"):
    _path = os.path.join(_REPO_ROOT, _name)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from pyre_starlette import PyreStarlette  # noqa: E402
from pyre_starlette.config import AppConfig, ServerConfig  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_config_env(monkeypatch):
    """The runner may export ``PYRE_*`` / ``SERVER_*`` variables that override config files."""
    for key in list(os.environ):
        if key.startswith(("PYRE_", "SERVER_")):
            monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture(autouse=True)
def _isolate_di_registry():
    """``DependencyContainer`` keeps a class-level registry; isolate it per test."""
    from pyre_injector import DependencyContainer

    snapshot = dict(DependencyContainer.dependency_definitions)
    try:
        yield
    finally:
        DependencyContainer.dependency_definitions.clear()
        DependencyContainer.dependency_definitions.update(snapshot)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Run every test inside an isolated temporary directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def app(workdir):
    """A ready ``PyreStarlette`` instance without any config file / datasource."""
    return PyreStarlette(
        app_config=AppConfig(server=ServerConfig(host="127.0.0.1", port=8000)),
        notice=False,
    )


@pytest.fixture
def client(app):
    from starlette.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def make_client():
    """Build a ``TestClient`` with ``raise_server_exceptions`` under control."""
    from starlette.testclient import TestClient

    def _make(app, raise_server_exceptions=True):
        return TestClient(app, raise_server_exceptions=raise_server_exceptions)

    return _make


@pytest.fixture
def toml_project(workdir):
    """Create a minimal pyre project layout (``resource/application*.toml``)."""
    resource = workdir / "resource"
    resource.mkdir(exist_ok=True)

    def _write(name, content):
        (resource / name).write_text(content, encoding="utf-8")

    _write(
        "application.toml",
        '[pyre.config]\nenv = "dev"\n',
    )
    _write(
        "application-dev.toml",
        '\n[pyre.datasource]\nurl = "sqlite:///./resource/probe.db"\necho = false\n',
    )
    return workdir
