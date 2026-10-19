"""OpenAPI generation and docs endpoints."""
import base64
from typing import List, Optional

import pytest
from pydantic import BaseModel, Field

from pyre_starlette import PyreStarlette, controller, route
from pyre_starlette.config import AppConfig, OpenapiConfig, ServerConfig
from pyre_starlette.openapi import PyreStarletteOpenapi


class ListQuery(BaseModel):
    keyword: Optional[str] = Field(default=None, description="关键词")
    page: int = Field(default=1, description="页码")


class ItemBody(BaseModel):
    name: str = Field(description="名称")


class ItemVo(BaseModel):
    id: int = Field(description="ID")
    name: str = Field(description="名称")


def _build_app(**openapi_kwargs):
    return PyreStarlette(
        app_config=AppConfig(server=ServerConfig(host="127.0.0.1", port=8000)),
        openapi_config=OpenapiConfig(enable=True, **openapi_kwargs),
        notice=False,
    )


def test_openapi_config_is_applied(client):
    app = _build_app(title="Demo API", version="1.2.3")
    spec = app.openapi.openapi()
    assert spec["info"]["title"] == "Demo API"
    assert spec["info"]["version"] == "1.2.3"


def test_openapi_config_accepts_dict():
    app = PyreStarlette(
        app_config=AppConfig(server=ServerConfig(host="127.0.0.1", port=8000)),
        openapi_config={"enable": True, "title": "From Dict"},
        notice=False,
    )
    assert app.openapi.openapi()["info"]["title"] == "From Dict"


def test_openapi_top_level_tags_accept_str_and_dict():
    app = _build_app(tags=["物品", {"name": "订单", "description": "订单相关"}])
    spec = app.openapi.openapi()
    assert spec["tags"] == [
        {"name": "物品"},
        {"name": "订单", "description": "订单相关"},
    ]



def test_docs_endpoints_are_served(app, client):
    for url in ("/docs", "/redoc", "/openapi.json"):
        r = client.get(url)
        assert r.status_code == 200, url
    assert client.get("/openapi.json").json()["openapi"]


def test_openapi_paths_and_operations(app):
    @controller("/items", summary="物品", router=app.router)
    class ItemController:
        @route("", methods=["GET"], summary="列表", query_model=ListQuery, response_model=List[ItemVo])
        def list_items(self, params: ListQuery):
            return []

        @route("", methods=["POST"], summary="创建", body_model=ItemBody, response_model=ItemVo)
        def create_item(self, params: ItemBody):
            return {"id": 1, "name": params.name}

    spec = app.openapi.openapi()
    paths = spec["paths"]
    assert "/items" in paths
    get_op = paths["/items"]["get"]
    post_op = paths["/items"]["post"]
    assert get_op["summary"] == "列表"
    assert post_op["summary"] == "创建"
    assert "requestBody" in post_op
    assert "200" in post_op["responses"]

    names = {p["name"] for p in get_op["parameters"]}
    assert {"keyword", "page"} <= names
    descriptions = {p["name"]: p.get("description") for p in get_op["parameters"]}
    assert descriptions["keyword"] == "关键词"

    schemas = spec["components"]["schemas"]
    assert "ItemVo" in schemas
    assert "ItemBody" in schemas


def test_openapi_excludes_internal_routes(app):
    spec = app.openapi.openapi()
    paths = spec["paths"]
    assert "/docs" not in paths
    assert "/openapi.json" not in paths
    assert "/redoc" not in paths


def test_openapi_tags_and_description(app):
    @app.router.route("/tagged", methods=["GET"], summary="s", description="d", tags=["tag-a", "tag-b"])
    def tagged():
        return {}

    op = app.openapi.openapi()["paths"]["/tagged"]["get"]
    assert op["description"] == "d"
    assert op["tags"] == ["tag-a", "tag-b"]


def test_openapi_security_scheme_from_auth(app):
    from pyre_starlette.security import HTTPTokenAuth

    auth = HTTPTokenAuth(security_name="MyBearer", verify_token_callback=lambda t: {"id": 1})

    @app.router.route("/secured", methods=["GET"])
    @auth.login_required
    def secured():
        return {}

    spec = app.openapi.openapi()
    schemes = spec["components"]["securitySchemes"]
    assert "MyBearer" in schemes
    assert schemes["MyBearer"]["scheme"] == "bearer"
    assert spec["paths"]["/secured"]["get"]["security"] == [{"MyBearer": []}]


def test_openapi_servers_default_port(app):
    spec = app.openapi.openapi()
    assert spec["servers"][0]["url"] == "http://127.0.0.1:8000"


def test_openapi_disabled():
    from starlette.testclient import TestClient

    app2 = PyreStarlette(
        app_config=AppConfig(server=ServerConfig(host="127.0.0.1", port=8000)),
        openapi_config=OpenapiConfig(enable=False),
        notice=False,
    )
    assert app2.openapi is None
    c = TestClient(app2)
    assert c.get("/docs").status_code == 404
    assert c.get("/openapi.json").status_code == 404


def test_doc_base_auth_protects_docs(app):
    from starlette.testclient import TestClient

    app2 = PyreStarlette(
        app_config=AppConfig(server=ServerConfig(host="127.0.0.1", port=8000)),
        openapi_config=OpenapiConfig(enable=True, username="u", password="p"),
        notice=False,
    )
    c = TestClient(app2)
    assert c.get("/openapi.json").status_code == 401
    token = base64.b64encode(b"u:p").decode()
    assert c.get("/openapi.json", headers={"Authorization": f"Basic {token}"}).status_code == 200


def test_openapi_generator_standalone():
    import os

    from pyre_starlette.openapi import docs as docs_module

    docs = PyreStarletteOpenapi(title="Standalone", version="9.9.9")
    assert docs.title == "Standalone"
    assert docs.doc_url == "/docs"
    template_folder = os.path.join(os.path.dirname(docs_module.__file__), "templates")
    page = docs.render_doc_page("swagger", template_folder)
    assert b"Swagger" in page.body
