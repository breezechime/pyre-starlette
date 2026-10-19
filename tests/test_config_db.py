"""Config loading (pyre-config) + database integration (sqlalchemy-db)."""
import os

import pytest

from pyre_starlette import PyreStarlette, controller, models, route


def test_config_file_is_loaded(toml_project):
    app = PyreStarlette(notice=False)
    assert app.app_config.pyre.datasource is not None
    assert "probe.db" in app.app_config.pyre.datasource.url
    assert app.app_config.pyre.config.env == "dev"
    assert app.db is not None


def test_configured_port_is_used(toml_project):
    (toml_project / "resource" / "application-dev.toml").write_text(
        '\n[pyre.datasource]\nurl = "sqlite:///./resource/probe.db"\n\n[server]\nport = 8123\n',
        encoding="utf-8",
    )
    app = PyreStarlette(notice=False)
    assert app.app_config.server.port == 8123


def test_database_crud_through_endpoints(toml_project):
    from starlette.testclient import TestClient

    app = PyreStarlette(notice=False)

    class ProbeThing(models.Model, models.PkMixin, models.TimestampMixin):
        __tablename__ = "probe_thing"
        __table_args__ = {"comment": "probe"}
        name = models.StringField(64, nullable=False, comment="name")

    app.db.create_all()

    @controller("/things", summary="things", router=app.router)
    class ThingController:
        @route("/add", methods=["POST"], summary="add")
        def add(self, name: str):
            thing = ProbeThing(name=name)
            thing.save()
            return {"id": thing.id, "name": thing.name}

        @route("/all", methods=["GET"], summary="all")
        def all_things(self):
            return {"count": ProbeThing.query.count()}

    client = TestClient(app)
    r = client.post("/things/add?name=hello")
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "hello"
    assert r.json()["id"]

    r = client.get("/things/all")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_database_middleware_opens_transaction(toml_project):
    from starlette.testclient import TestClient

    from pyre_starlette.models.database_middleware import DatabaseMiddleware

    app = PyreStarlette(notice=False)
    classes = [mw.cls for mw in app.user_middleware]
    assert DatabaseMiddleware in classes

    client = TestClient(app)
    assert client.get("/").status_code == 200


def test_db_component_is_injected(toml_project):
    from pyre_injector import autowired

    from pyre_starlette import SQLAlchemyDB

    app = PyreStarlette(notice=False)
    assert isinstance(app.db, SQLAlchemyDB)
    assert autowired(SQLAlchemyDB) is app.db


def test_env_variable_overrides_config_file(toml_project, monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "9999")
    app = PyreStarlette(notice=False)
    assert app.app_config.server.port == 9999
