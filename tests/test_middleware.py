"""Middleware, request context and background tasks."""
import asyncio
import time

import pytest

from pyre_starlette import Request, Response, get_request, try_get_request, with_request_context


def test_request_context_is_available_inside_endpoint(app, client):
    @app.router.route("/ctx", methods=["GET"])
    def ctx():
        request = get_request()
        return {
            "path": request.url.path,
            "same": try_get_request() is request,
        }

    assert client.get("/ctx").json() == {"path": "/ctx", "same": True}


def test_request_context_is_cleared_after_request(app, client):
    @app.router.route("/clear", methods=["GET"])
    def clear():
        return {"ok": True}

    assert client.get("/clear").json() == {"ok": True}
    assert try_get_request() is None
    with pytest.raises(RuntimeError):
        get_request()


def test_get_request_without_context_raises():
    with pytest.raises(RuntimeError):
        get_request()


def test_with_request_context_wrapper(app, client):
    @app.router.route("/wrapped", methods=["GET"])
    @with_request_context
    async def wrapped(request: Request):
        return {"path": get_request().url.path}

    assert client.get("/wrapped").json() == {"path": "/wrapped"}


def test_request_context_middleware_is_first(app):
    from pyre_starlette.middleware import RequestContextMiddleware

    first = app.user_middleware[0]
    assert first.cls is RequestContextMiddleware


def test_custom_middleware_decorator(app, client):
    order = []

    @app.middleware()
    async def mw(request, call_next):
        order.append("before")
        response = await call_next(request)
        response.headers["X-Custom"] = "yes"
        order.append("after")
        return response

    @app.router.route("/mw", methods=["GET"])
    def mw_ep():
        order.append("handler")
        return {"ok": True}

    r = client.get("/mw")
    assert r.json() == {"ok": True}
    assert r.headers["X-Custom"] == "yes"
    assert order == ["before", "handler", "after"]


def test_add_middleware_keeps_request_context_first(app):
    from pyre_starlette.middleware import RequestContextMiddleware
    from pyre_starlette import Middleware

    class MyMiddleware:
        def __init__(self, app, **kwargs):
            self.app = app

        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)

    app.add_middleware(MyMiddleware)
    assert app.user_middleware[0].cls is RequestContextMiddleware
    assert app.user_middleware[1].cls is MyMiddleware


def test_cors_middleware(app, client):
    from pyre_starlette.middleware import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.router.route("/cors", methods=["GET"])
    def cors():
        return {"ok": True}

    r = client.get("/cors", headers={"Origin": "http://example.com"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"


def test_background_task_sync_and_async(app, client):
    calls = []

    def sync_job(value):
        calls.append(("sync", value))

    async def async_job(value):
        calls.append(("async", value))

    @app.router.route("/bg", methods=["GET"])
    async def bg():
        app.add_background_task(sync_job, 1)
        app.add_background_task(async_job, 2)
        return {"ok": True}

    assert client.get("/bg").json() == {"ok": True}
    deadline = time.time() + 2
    while len(calls) < 2 and time.time() < deadline:
        time.sleep(0.02)
    assert ("sync", 1) in calls
    assert ("async", 2) in calls


def test_background_task_error_callback(app, client):
    errors = []

    def failing():
        raise RuntimeError("bg fail")

    @app.router.route("/bgfail", methods=["GET"])
    async def bgfail():
        app.add_background_task(failing, on_error=lambda e: errors.append(str(e)))
        return {"ok": True}

    assert client.get("/bgfail").json() == {"ok": True}
    deadline = time.time() + 2
    while not errors and time.time() < deadline:
        time.sleep(0.02)
    assert errors == ["bg fail"]
