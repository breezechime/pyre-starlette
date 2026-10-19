"""Routing: paths, prefixes, nested routers, registration order, methods, 404/405."""
import pytest

from pyre_starlette import PyreStarlette, Router, controller, route


def test_app_level_route_decorators(app, client):
    @app.router.get("/a", summary="a")
    def a():
        return {"a": 1}

    @app.router.post("/b")
    def b():
        return {"b": 2}

    @app.router.put("/c")
    def c():
        return {"c": 3}

    @app.router.delete("/d")
    def d():
        return {"d": 4}

    @app.router.patch("/e")
    def e():
        return {"e": 5}

    assert client.get("/a").json() == {"a": 1}
    assert client.post("/b").json() == {"b": 2}
    assert client.put("/c").json() == {"c": 3}
    assert client.delete("/d").json() == {"d": 4}
    assert client.patch("/e").json() == {"e": 5}


def test_path_parameters_and_types(app, client):
    @app.router.route("/int/{value:int}", methods=["GET"])
    def as_int(value: int):
        return {"value": value, "type": type(value).__name__}

    @app.router.route("/float/{value:float}", methods=["GET"])
    def as_float(value: float):
        return {"value": value}

    @app.router.route("/path/{rest:path}", methods=["GET"])
    def as_path(rest: str):
        return {"rest": rest}

    r = client.get("/int/42")
    assert r.status_code == 200 and r.json()["value"] == 42 and r.json()["type"] == "int"
    assert client.get("/float/1.5").json()["value"] == 1.5
    assert client.get("/path/a/b/c").json()["rest"] == "a/b/c"
    # {value:int} 转换器不匹配非数字片段，路由整体不匹配
    assert client.get("/int/not-an-int").status_code == 404


def test_controller_route_registration_keeps_definition_order(app, client):
    """Controller routes must be registered in declaration order, not alphabetically."""

    @controller("/ordered", summary="ordered", router=app.router)
    class OrderedController:
        @route("/zebra", methods=["GET"])
        def zebra(self):
            return {"n": "zebra"}

        @route("/apple", methods=["GET"])
        def apple(self):
            return {"n": "apple"}

        @route("/mango", methods=["GET"])
        def mango(self):
            return {"n": "mango"}

    ordered = [r.path for r in app.router.iter_routes() if r.path.startswith("/ordered/")]
    assert ordered == ["/ordered/zebra", "/ordered/apple", "/ordered/mango"]


def test_static_route_before_param_route_wins(app, client):
    @controller("/item", summary="item", router=app.router)
    class ItemRouteController:
        @route("/list", methods=["GET"])
        def listing(self):
            return {"kind": "list"}

        @route("/{item_id}", methods=["GET"])
        def detail(self, item_id: str):
            return {"kind": "detail", "id": item_id}

    assert client.get("/item/list").json() == {"kind": "list"}
    assert client.get("/item/xyz").json() == {"kind": "detail", "id": "xyz"}


def test_controller_mounting_with_router_and_prefix(app, client):
    api = Router()

    @controller("/things", summary="things", router=api)
    class ThingController:
        @route("/{thing_id}", methods=["GET"], summary="get")
        def get_thing(self, thing_id: str):
            return {"id": thing_id}

        @route("", methods=["GET"], summary="list")
        def list_things(self):
            return {"items": []}

    app.add_router(api, prefix="/api")

    assert client.get("/api/things/7").json() == {"id": "7"}
    assert client.get("/api/things").json() == {"items": []}


def test_nested_router_prefix_is_kept(app, client):
    leaf = Router(prefix="/leaf")

    @leaf.route("/ping", methods=["GET"])
    def ping():
        return {"pong": True}

    middle = Router(prefix="/middle")
    middle.add_router(leaf, prefix="/inner")

    app.add_router(middle, prefix="/outer")

    r = client.get("/outer/middle/inner/leaf/ping")
    assert r.status_code == 200, r.text
    assert r.json() == {"pong": True}


def test_route_metadata_is_attached(app):
    @app.router.route("/meta", methods=["GET"], summary="s", description="d", tags=["t"])
    def meta():
        return {}

    found = [r for r in app.router.iter_routes() if r.path == "/meta"][0]
    assert found.summary == "s"
    assert found.description == "d"
    assert found.tags == ["t"]
    assert "GET" in found.methods


def test_404_and_405(app, client):
    @app.router.route("/only-get", methods=["GET"])
    def only_get():
        return {}

    assert client.get("/nope").status_code == 404
    assert client.post("/only-get").status_code in (404, 405)


def test_router_get_route_lookup(app):
    @app.router.route("/lookup", methods=["GET"], name="lookup_ep")
    def lookup():
        return {}

    found = app.router.get_route("lookup_ep")
    assert found is not None
    assert found.path == "/lookup"
    assert app.router.get_route("missing") is None


def test_controller_inheritance_keeps_routes(app, client):
    class BaseController:
        @route("/base", methods=["GET"], summary="base")
        def base(self):
            return {"base": True}

    class ChildController(BaseController):
        @route("/child", methods=["GET"], summary="child")
        def child(self):
            return {"child": True}

    ChildController = controller("/inh", router=app.router)(ChildController)

    assert client.get("/inh/base").json() == {"base": True}
    assert client.get("/inh/child").json() == {"child": True}


def test_docs_routes_registered_by_default(app):
    paths = {r.path for r in app.router.iter_routes()}
    assert "/docs" in paths
    assert "/openapi.json" in paths
    assert "/redoc" in paths
    assert "/" in paths
