"""Dependency injection integration with ``pyre-injector``."""
import pytest

from pyre_starlette import Controller, controller, route
from pyre_starlette.service import BaseService


class Repository:
    def __init__(self):
        self.data = {"1": "one"}


class RepositoryService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def get(self, key: str):
        return self.repo.data.get(key)


def test_provider_inside_endpoint(app, client):
    from pyre_starlette import provider

    app.dependency_container.inject(Repository)
    app.dependency_container.inject(RepositoryService)

    @app.router.route("/di", methods=["GET"])
    def di(key: str = "1"):
        return {"value": provider(RepositoryService).get(key)}

    assert client.get("/di").json() == {"value": "one"}
    assert client.get("/di?key=none").json() == {"value": None}


def test_controller_constructor_injection(app, client):
    app.dependency_container.inject(Repository)
    app.dependency_container.inject(RepositoryService)

    @controller("/svc", summary="svc", router=app.router)
    class SvcController:
        def __init__(self, service: RepositoryService):
            self.service = service

        @route("/{key}", methods=["GET"])
        def get(self, key: str):
            return {"value": self.service.get(key)}

    assert client.get("/svc/1").json() == {"value": "one"}


def test_injected_instance_is_used(app, client):
    repo = Repository()
    repo.data["2"] = "two"
    app.dependency_container.inject(repo)  # 手动注入实例

    @app.router.route("/inst", methods=["GET"])
    def inst():
        from pyre_starlette import provider

        return {"value": provider(Repository).data.get("2")}

    assert client.get("/inst").json() == {"value": "two"}


def test_missing_dependency_reports_position(app):
    from pyre_injector import DependencyError

    class NeedsMissing:
        def __init__(self, missing: "NotRegistered"):  # noqa: F821
            self.missing = missing

    app.dependency_container.inject(NeedsMissing, solve_init=False)
    with pytest.raises(DependencyError) as info:
        app.dependency_container.provider(NeedsMissing)
    assert "test_di.py" in str(info.value)


def test_circular_dependency_is_reported(app):
    from pyre_injector import DependencyError

    class CycleA:
        def __init__(self, b: "CycleB"):
            self.b = b

    class CycleB:
        def __init__(self, a: CycleA):
            self.a = a

    app.dependency_container.inject(CycleA, solve_init=False)
    app.dependency_container.inject(CycleB, solve_init=False)
    with pytest.raises(DependencyError):
        app.dependency_container.provider(CycleA)


def test_baseservice_subclass_is_registered():
    class MyService(BaseService):
        model_class = None

    from pyre_injector import DependencyContainer

    assert "MyService" in DependencyContainer.dependency_definitions


def test_baseservice_provider_helper(app, client):
    app.dependency_container.inject(Repository)

    class HelperService(BaseService):
        model_class = None

        def repo(self):
            return self.provider(Repository)

    service = HelperService()
    assert isinstance(service.repo(), Repository)


def test_controller_autowired_helper(app, client):
    app.dependency_container.inject(Repository)

    @controller("/helper", summary="helper", router=app.router)
    class HelperController(Controller):
        @route("/ping", methods=["GET"])
        def ping(self):
            return {"ok": self.autowired(Repository) is not None}

    assert client.get("/helper/ping").json() == {"ok": True}
