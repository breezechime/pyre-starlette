"""Response serialization: raw values, pydantic models, response_model, encoders."""
import datetime
import enum
import threading
from typing import List, Optional

import pytest
from pydantic import BaseModel
from starlette.responses import JSONResponse, PlainTextResponse

from pyre_starlette import Response, jsonable_encoder


def test_dict_and_list_payloads(app, client):
    @app.router.route("/dict", methods=["GET"])
    def as_dict():
        return {"a": 1, "b": [1, 2, 3]}

    @app.router.route("/list", methods=["GET"])
    def as_list():
        return [1, 2, 3]

    @app.router.route("/scalar", methods=["GET"])
    def as_scalar():
        return 42

    assert client.get("/dict").json() == {"a": 1, "b": [1, 2, 3]}
    assert client.get("/list").json() == [1, 2, 3]
    assert client.get("/scalar").json() == 42


def test_raw_response_is_passed_through(app, client):
    @app.router.route("/text", methods=["GET"])
    def as_text():
        return PlainTextResponse("hello", status_code=201)

    @app.router.route("/json", methods=["GET"])
    def as_json():
        return JSONResponse({"ok": True}, status_code=202)

    r = client.get("/text")
    assert r.status_code == 201 and r.text == "hello"
    r = client.get("/json")
    assert r.status_code == 202 and r.json() == {"ok": True}


def test_basemodel_response(app, client):
    class Vo(BaseModel):
        id: int
        name: str

    @app.router.route("/vo", methods=["GET"])
    def vo():
        return Vo(id=1, name="a")

    assert client.get("/vo").json() == {"id": 1, "name": "a"}


def test_response_model_validation(app, client):
    class Vo(BaseModel):
        id: int
        name: str

    @app.router.route("/valid", methods=["GET"], response_model=Vo)
    def valid():
        return {"id": 1, "name": "a"}

    @app.router.route("/coerce", methods=["GET"], response_model=Vo)
    def coerce():
        return {"id": "5", "name": "a"}

    @app.router.route("/invalid", methods=["GET"], response_model=Vo)
    def invalid():
        return {"id": "not-a-number", "name": "a"}

    assert client.get("/valid").json() == {"id": 1, "name": "a"}
    assert client.get("/coerce").json() == {"id": 5, "name": "a"}
    assert client.get("/invalid").status_code == 500


def test_response_model_list(app, client):
    class Vo(BaseModel):
        id: int

    @app.router.route("/many", methods=["GET"], response_model=List[Vo])
    def many():
        return [{"id": 1}, {"id": 2}]

    assert client.get("/many").json() == [{"id": 1}, {"id": 2}]


def test_response_model_of_scalar(app, client):
    @app.router.route("/count", methods=["GET"], response_model=int)
    def count():
        return 7

    assert client.get("/count").json() == 7


def test_response_model_skipped_for_non_200(app, client):
    class Vo(BaseModel):
        id: int

    @app.router.route("/created", methods=["POST"], response_model=Vo, status_code=201)
    def created():
        return {"id": 1}

    r = client.post("/created")
    assert r.status_code == 201


def test_status_code_option(app, client):
    @app.router.route("/accepted", methods=["POST"], status_code=202)
    def accepted():
        return {"ok": True}

    assert client.post("/accepted").status_code == 202


def test_jsonable_encoder_basics():
    class Color(enum.Enum):
        RED = "red"

    payload = {
        "dt": datetime.datetime(2026, 1, 2, 3, 4, 5),
        "d": datetime.date(2026, 1, 2),
        "c": Color.RED,
        "s": {1, 2},
        "nested": [{"x": 1}],
        "raw": "text",
        "num": 1.5,
        "none": None,
    }
    out = jsonable_encoder(payload)
    assert out["dt"] == "2026-01-02 03:04:05"
    assert out["d"] == "2026-01-02"
    assert out["c"] == "red"
    assert sorted(out["s"]) == [1, 2]
    assert out["nested"] == [{"x": 1}]
    assert out["none"] is None


def test_jsonable_encoder_basemodel():
    class Model(BaseModel):
        a: int
        b: Optional[str] = None

    assert jsonable_encoder(Model(a=1)) == {"a": 1, "b": None}


def test_jsonable_encoder_cyclic_reference():
    data = {}
    data["self"] = data
    out = jsonable_encoder(data)
    assert out["self"] is None


def test_jsonable_encoder_is_reentrant_across_threads():
    """The recursion guard must not leak state between concurrent calls."""
    results = {}

    def worker(key, payload):
        results[key] = jsonable_encoder(payload)

    payloads = {i: {"k": [i] * 5} for i in range(8)}
    threads = [threading.Thread(target=worker, args=(i, payloads[i])) for i in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == {i: {"k": [i] * 5} for i in payloads}
