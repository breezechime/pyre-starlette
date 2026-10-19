"""Parameter injection: Query / Body / Path / Header / Cookie, defaults, models, errors."""
from typing import Annotated, List, Optional

import pytest
from pydantic import BaseModel, Field

from pyre_starlette import Body, Cookie, Header, Path, Query


def test_plain_query_params_and_defaults(app, client):
    @app.router.route("/q", methods=["GET"])
    def q(keyword: str, page: int = 1, size: int = 20, flag: bool = False):
        return {"keyword": keyword, "page": page, "size": size, "flag": flag}

    assert client.get("/q?keyword=abc").json() == {"keyword": "abc", "page": 1, "size": 20, "flag": False}
    assert client.get("/q?keyword=a&page=3&size=5&flag=true").json() == {
        "keyword": "a", "page": 3, "size": 5, "flag": True,
    }


def test_optional_query_param(app, client):
    @app.router.route("/opt", methods=["GET"])
    def opt(keyword: Optional[str] = None, page: int = 1):
        return {"keyword": keyword, "page": page}

    assert client.get("/opt").json() == {"keyword": None, "page": 1}
    assert client.get("/opt?keyword=x&page=2").json() == {"keyword": "x", "page": 2}


def test_missing_required_query_param_returns_400(app, client):
    @app.router.route("/req", methods=["GET"])
    def req(keyword: str):
        return {"keyword": keyword}

    r = client.get("/req")
    assert r.status_code == 400
    assert "keyword" in r.json()["msg"]


def test_invalid_query_type_returns_400(app, client):
    @app.router.route("/typed", methods=["GET"])
    def typed(page: int):
        return {"page": page}

    r = client.get("/typed?page=not-int")
    assert r.status_code == 400
    assert "page" in r.json()["msg"]


def test_annotated_query_with_default(app, client):
    @app.router.route("/an", methods=["GET"])
    def an(
        keyword: Annotated[str, Query(description="关键字")],
        page: Annotated[int, Query(default=1)] = 1,
    ):
        return {"keyword": keyword, "page": page}

    assert client.get("/an?keyword=k").json() == {"keyword": "k", "page": 1}
    assert client.get("/an?keyword=k&page=9").json() == {"keyword": "k", "page": 9}


def test_annotated_header_and_cookie(app, client):
    @app.router.route("/hc", methods=["GET"])
    def hc(
        x_token: Annotated[Optional[str], Header()] = None,
        sid: Annotated[Optional[str], Cookie()] = None,
        count: Annotated[int, Header()] = 0,
    ):
        return {"x_token": x_token, "sid": sid, "count": count}

    r = client.get("/hc", headers={"x-token": "tok", "count": "5"}, cookies={"sid": "s1"})
    assert r.json() == {"x_token": "tok", "sid": "s1", "count": 5}
    # 缺失时使用默认值
    assert client.get("/hc").json() == {"x_token": None, "sid": None, "count": 0}


def test_annotated_path_param(app, client):
    @app.router.route("/p/{item_id}", methods=["GET"])
    def p(item_id: Annotated[int, Path(description="ID")]):
        return {"item_id": item_id, "type": type(item_id).__name__}

    assert client.get("/p/12").json() == {"item_id": 12, "type": "int"}


def test_query_model(app, client):
    class ListQuery(BaseModel):
        keyword: Optional[str] = Field(default=None, description="关键词")
        page: int = 1

    @app.router.route("/model", methods=["GET"], query_model=ListQuery)
    def model(params: ListQuery):
        return {"keyword": params.keyword, "page": params.page}

    assert client.get("/model?keyword=k&page=2").json() == {"keyword": "k", "page": 2}
    assert client.get("/model").json() == {"keyword": None, "page": 1}
    # 类型非法 -> 400
    assert client.get("/model?page=abc").status_code == 400


def test_body_model(app, client):
    class CreateBody(BaseModel):
        name: str
        qty: int = 1

    @app.router.route("/create", methods=["POST"], body_model=CreateBody)
    def create(params: CreateBody):
        return {"name": params.name, "qty": params.qty}

    assert client.post("/create", json={"name": "x"}).json() == {"name": "x", "qty": 1}
    assert client.post("/create", json={"name": "x", "qty": 7}).json() == {"name": "x", "qty": 7}
    # 必填缺失 -> 400
    assert client.post("/create", json={}).status_code == 400
    # 非法 JSON -> 400
    r = client.post("/create", content=b"{bad json", headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_annotated_body_param(app, client):
    class Payload(BaseModel):
        a: int

    @app.router.route("/ab", methods=["POST"])
    def ab(payload: Annotated[Payload, Body()]):
        return {"a": payload.a}

    assert client.post("/ab", json={"a": 3}).json() == {"a": 3}
    assert client.post("/ab", json={}).status_code == 400


def test_header_model(app, client):
    class Headers(BaseModel):
        x_token: str = Field(alias="x-token")

    @app.router.route("/hm", methods=["GET"], header_model=Headers)
    def hm(headers: Headers):
        return {"token": headers.x_token}

    assert client.get("/hm", headers={"x-token": "abc"}).json() == {"token": "abc"}


def test_cookie_model(app, client):
    class Cookies(BaseModel):
        sid: str

    @app.router.route("/cm", methods=["GET"], cookie_model=Cookies)
    def cm(cookies: Cookies):
        return {"sid": cookies.sid}

    assert client.get("/cm", cookies={"sid": "cookie-1"}).json() == {"sid": "cookie-1"}


def test_request_parameter_is_injected(app, client):
    from pyre_starlette import Request

    @app.router.route("/reqobj", methods=["GET"])
    def reqobj(request: Request, page: int = 1):
        return {"method": request.method, "page": page, "url": str(request.url.path)}

    r = client.get("/reqobj?page=4")
    assert r.json() == {"method": "GET", "page": 4, "url": "/reqobj"}


def test_async_endpoint(app, client):
    @app.router.route("/async", methods=["GET"])
    async def async_ep(n: int = 2):
        return {"n": n * 2}

    assert client.get("/async?n=5").json() == {"n": 10}
    assert client.get("/async").json() == {"n": 4}


def test_body_from_form(app, client):
    @app.router.route("/form", methods=["POST"])
    def form(name: Annotated[str, Body()]):
        return {"name": name}

    r = client.post("/form", data={"name": "form-name"})
    assert r.status_code == 200 and r.json() == {"name": "form-name"}
