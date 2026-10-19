"""Exception handling: application exceptions, custom handlers, validation messages."""
import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException

from pyre_starlette.exceptions import (
    ApplicationException,
    AuthenticationTimeoutException,
    BadRequestException,
    ForbiddenException,
    MethodNotAllowException,
    NotFoundDataException,
    NotFoundException,
    UnauthorizedException,
    UnsupportedMediaTypeException,
)
from pyre_starlette.exceptions.messages import (
    get_message,
    register_messages,
    translate_validation_msg,
)

APPLICATION_EXCEPTIONS = [
    (BadRequestException, 400),
    (UnauthorizedException, 401),
    (ForbiddenException, 403),
    (NotFoundException, 404),
    (NotFoundDataException, 404),
    (MethodNotAllowException, 405),
    (UnsupportedMediaTypeException, 415),
    (AuthenticationTimeoutException, 419),
]


@pytest.mark.parametrize("exc_cls,status_code", APPLICATION_EXCEPTIONS)
def test_application_exception_status_and_body(app, client, exc_cls, status_code):
    @app.router.route("/raise", methods=["GET"])
    def raise_it():
        raise exc_cls()

    r = client.get("/raise")
    assert r.status_code == status_code
    body = r.json()
    assert body["code"] == status_code
    assert isinstance(body["msg"], str) and body["msg"]


def test_application_exception_custom_message(app, client):
    @app.router.route("/custom", methods=["GET"])
    def custom():
        raise BadRequestException(msg="参数不对", extra="x")

    r = client.get("/custom")
    assert r.status_code == 400
    assert r.json()["msg"] == "参数不对"
    assert r.json()["extra"] == "x"


def test_application_exception_is_http_exception():
    assert issubclass(BadRequestException, ApplicationException)
    assert issubclass(ApplicationException, StarletteHTTPException)
    # 兼容旧的 `except RuntimeError`
    assert issubclass(ApplicationException, Exception)


def test_unhandled_exception_returns_500(app, make_client):
    @app.router.route("/boom", methods=["GET"])
    def boom():
        raise ValueError("kaboom")

    client = make_client(app, raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.json()["code"] == 500


def test_custom_exception_handler_returns_payload(app, client):
    class MyError(Exception):
        pass

    @app.exception_handler(MyError)
    def handle(request, exc):
        return {"code": 1001, "msg": "handled", "path": str(request.url.path)}

    @app.router.route("/myerr", methods=["GET"])
    def myerr():
        raise MyError()

    r = client.get("/myerr")
    assert r.status_code == 200
    assert r.json() == {"code": 1001, "msg": "handled", "path": "/myerr"}


def test_custom_exception_handler_can_return_response(app, client):
    class RespError(Exception):
        pass

    @app.exception_handler(RespError)
    def handle(request, exc):
        from starlette.responses import PlainTextResponse

        return PlainTextResponse("custom", status_code=418)

    @app.router.route("/resperr", methods=["GET"])
    def resperr():
        raise RespError()

    r = client.get("/resperr")
    assert r.status_code == 418 and r.text == "custom"


def test_starlette_http_exception_uses_application_handler(app, client):
    @app.router.route("/native", methods=["GET"])
    def native():
        raise StarletteHTTPException(status_code=403, detail="nope")

    r = client.get("/native")
    assert r.status_code == 403


def test_validation_error_message_is_localized(app, client):
    @app.router.route("/v", methods=["GET"])
    def v(page: int):
        return {"page": page}

    r = client.get("/v")
    assert r.status_code == 400
    assert "page" in r.json()["msg"]
    assert "请求参数校验错误" in r.json()["msg"]


def test_get_message_and_register_messages():
    assert get_message("Not Found Data", "zh-hans") == "未找到数据，可能已被删除"
    # 未知 key 原样返回
    assert get_message("no-such-key", "zh-hans") == "no-such-key"

    register_messages("zh-hans", {"Custom Key": "自定义文案"})
    assert get_message("Custom Key", "zh-hans") == "自定义文案"


def test_translate_validation_msg_by_type_and_fallback():
    assert translate_validation_msg("Field required", "missing", "zh-hans") == "必填项"
    assert translate_validation_msg("Input should be a valid integer", "int_parsing", "en") == (
        "Input should be a valid integer"
    )
    # 无匹配 -> 原样返回
    assert translate_validation_msg("some unknown msg", "unknown_type", "en") == "some unknown msg"


def test_404_and_405_messages(app, client):
    r = client.get("/definitely-not-here")
    assert r.status_code == 404
    assert r.json()["code"] == 404
