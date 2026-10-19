"""Security helpers: token / basic / api-key authentication."""
import base64

import pytest

from pyre_starlette.security import (
    HTTPApiKeyAuth,
    HTTPBasicAuth,
    HTTPTokenAuth,
)


def test_token_auth_success_and_failure(app, client):
    auth = HTTPTokenAuth(verify_token_callback=lambda token: {"id": 7} if token == "good" else None)

    @app.router.route("/secure", methods=["GET"])
    @auth.login_required
    def secure():
        return {"user": auth.current_user()}

    assert client.get("/secure", headers={"Authorization": "Bearer good"}).json() == {"user": {"id": 7}}
    assert client.get("/secure", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get("/secure").status_code == 401


def test_token_auth_get_token(app, client):
    auth = HTTPTokenAuth(verify_token_callback=lambda token: True)

    @app.router.route("/tok", methods=["GET"])
    @auth.login_required
    def tok():
        return {"token": auth.get_token()}

    assert client.get("/tok", headers={"Authorization": "Bearer abc"}).json() == {"token": "abc"}


def test_token_auth_optional_allows_anonymous(app, client):
    auth = HTTPTokenAuth(verify_token_callback=lambda token: {"id": 1})

    @app.router.route("/opt", methods=["GET"])
    @auth.login_required(optional=True)
    def opt():
        return {"user": auth.current_user()}

    assert client.get("/opt").json() == {"user": None}
    assert client.get("/opt", headers={"Authorization": "Bearer t"}).json() == {"user": {"id": 1}}


def test_basic_auth_success_and_failure(app, client):
    def verify(username, password):
        return {"name": username} if (username, password) == ("u", "p") else None

    auth = HTTPBasicAuth(verify_password_callback=verify)

    @app.router.route("/basic", methods=["GET"])
    @auth.login_required
    def basic():
        return {"user": auth.current_user()}

    token = base64.b64encode(b"u:p").decode()
    assert client.get("/basic", headers={"Authorization": f"Basic {token}"}).json() == {"user": {"name": "u"}}
    bad = base64.b64encode(b"u:wrong").decode()
    assert client.get("/basic", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    assert client.get("/basic").status_code == 401


def test_api_key_auth_header_location(app, client):
    auth = HTTPApiKeyAuth(api_key_name="X-API-Key", verify_api_key_callback=lambda key: key == "secret")

    @app.router.route("/api-key", methods=["GET"])
    @auth.login_required
    def api_key():
        return {"ok": auth.current_user()}

    assert client.get("/api-key", headers={"X-API-Key": "secret"}).json() == {"ok": True}
    assert client.get("/api-key", headers={"X-API-Key": "nope"}).status_code == 401


def test_api_key_auth_query_location(app, client):
    auth = HTTPApiKeyAuth(api_key_name="key", location="query", verify_api_key_callback=lambda key: key == "k")

    @app.router.route("/qkey", methods=["GET"])
    @auth.login_required
    def qkey():
        return {"ok": True}

    assert client.get("/qkey?key=k").json() == {"ok": True}
    assert client.get("/qkey?key=z").status_code == 401


def test_auth_error_includes_www_authenticate(app, client):
    auth = HTTPTokenAuth(verify_token_callback=lambda token: None)

    @app.router.route("/wa", methods=["GET"])
    @auth.login_required
    def wa():
        return {}

    r = client.get("/wa")
    assert r.status_code == 401
    assert "www-authenticate" in {k.lower() for k in r.headers}


def test_role_check_raises_forbidden(app, client):
    class RoleAuth(HTTPTokenAuth):
        def has_role(self, *role, method="and"):
            return False

    auth = RoleAuth(verify_token_callback=lambda token: {"id": 1})

    @app.router.route("/role", methods=["GET"])
    @auth.login_required(roles=["admin"])
    def role():
        return {}

    r = client.get("/role", headers={"Authorization": "Bearer t"})
    assert r.status_code == 403


def test_authorize_false_returns_forbidden(app, client):
    class DenyAuth(HTTPTokenAuth):
        def authorize(self, request, user, roles=None, permissions=None, *args, **kwargs):
            return False

    auth = DenyAuth(verify_token_callback=lambda token: {"id": 1})

    @app.router.route("/deny", methods=["GET"])
    @auth.login_required(roles=["admin"])
    def deny():
        return {}

    assert client.get("/deny", headers={"Authorization": "Bearer t"}).status_code == 403
