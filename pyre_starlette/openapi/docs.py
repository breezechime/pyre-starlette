import base64
import os
import secrets
from typing import Any, List, Optional, Union

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from .assets import (
    GOOGLE_FONTS_URL,
    RAPIDOC_JS_URL,
    REDOC_JS_URL,
    SWAGGER_FAVICON_URL,
    SWAGGER_UI_CSS_URL,
    SWAGGER_UI_JS_URL,
)
from .generator import (
    DESCRIPTION_KEY,
    SUMMARY_KEY,
    TAGS_KEY,
    PyreStarletteOpenapiGenerator,
)
from .models import Contact, License, Server

try:
    from jinja2 import Template
except ImportError:
    Template = None


class PyreStarletteOpenapi:
    """Pyre Starlette OpenAPI 文档服务。"""

    def __init__(
        self,
        pyre_app: Optional[Any] = None,
        title: str = "Pyre Starlette",
        version: str = "0.0.1",
        openapi_version: str = "3.0.2",
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        terms_of_service: Optional[str] = None,
        contact: Optional[Union[dict, Contact]] = None,
        license: Optional[Union[dict, License]] = None,
        servers: Optional[List[Union[dict, Server]]] = None,
        responses: Optional[List[Union[dict, dict]]] = None,
        doc_url: str = "/docs",
        redoc_url: Optional[str] = "/redoc",
        openapi_url: str = "/openapi.json",
        ui: str = "swagger",
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs: Any,
    ):
        self.title = title
        self.version = version
        self.openapi_version = openapi_version
        self.summary = summary
        self.description = description
        self.tags = tags or []
        self.terms_of_service = terms_of_service
        self.contact = contact
        self.license = license
        self.servers = servers
        self.doc_url = doc_url
        self.redoc_url = redoc_url
        self.openapi_url = openapi_url
        self.ui = ui
        self.username = username
        self.password = password
        self.responses = responses
        self.pyre_app = pyre_app
        self.kwargs = kwargs
        self.security_schemes: dict[str, dict] = {}

        if pyre_app is not None:
            self.init_app(pyre_app)

    def init_app(self, pyre_app: Any) -> None:
        """注册文档与 OpenAPI JSON 路由。"""
        self.pyre_app = pyre_app
        template_folder = os.path.join(os.path.dirname(__file__), "templates")

        @pyre_app.get(self.doc_url, include_openapi=False)
        def doc_html(request: Request):
            auth_response = self.check_auth(request)
            if auth_response is not None:
                return auth_response

            ui = request.query_params.get("ui") or self.ui
            if ui not in {"redoc", "swagger", "rapidoc"}:
                ui = "swagger"
            return self.render_doc_page(ui, template_folder)

        if self.redoc_url:

            @pyre_app.get(self.redoc_url, include_openapi=False)
            def redoc_html(request: Request):
                auth_response = self.check_auth(request)
                if auth_response is not None:
                    return auth_response
                return self.render_doc_page("redoc", template_folder)

        @pyre_app.get(
            self.openapi_url,
            response_model_exclude_unset=True,
            include_openapi=False,
        )
        def openapi_json(request: Request):
            auth_response = self.check_auth(request)
            if auth_response is not None:
                return auth_response
            return self.openapi()

    def render_doc_page(self, ui: str, template_folder: str) -> HTMLResponse:
        template_path = os.path.join(template_folder, f"{ui}.html")
        with open(template_path, "r", encoding="utf-8") as file:
            template = file.read()
        content = self.render_template(
            template,
            ui=ui,
            title=self._doc_title(ui),
            spec_url=self.openapi_url,
            swagger_css_url=SWAGGER_UI_CSS_URL,
            swagger_js_url=SWAGGER_UI_JS_URL,
            redoc_js_url=REDOC_JS_URL,
            rapidoc_js_url=RAPIDOC_JS_URL,
            google_fonts_url=GOOGLE_FONTS_URL,
            favicon_url=SWAGGER_FAVICON_URL,
            oauth2_redirect_url=f"{self.doc_url.rstrip('/')}/oauth2-redirect",
        )
        return HTMLResponse(content)

    def _doc_title(self, ui: str) -> str:
        labels = {
            "swagger": "Swagger UI",
            "redoc": "ReDoc",
            "rapidoc": "RapiDoc",
        }
        return f"{self.title} - {labels.get(ui, 'API Docs')}"

    def render_template(self, template: str, **context: Any) -> str:
        if Template is not None:
            return Template(template).render(**context)
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(f"{{{{ {key} }}}}", str(value))
        return rendered

    def check_auth(self, request: Request) -> Optional[Response]:
        if not self.username or not self.password:
            return None

        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Basic "):
            try:
                decoded = base64.b64decode(authorization[6:]).decode("utf-8")
                username, _, password = decoded.partition(":")
                if secrets.compare_digest(username, self.username) and secrets.compare_digest(
                    password, self.password
                ):
                    return None
            except Exception:
                pass

        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="OpenAPI"'},
        )

    def openapi(self) -> dict:
        return PyreStarletteOpenapiGenerator(self).generate()

    def doc(
        self,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ):
        """为 handler 附加 OpenAPI 元数据的装饰器。"""

        def decorator(func):
            setattr(func, SUMMARY_KEY, summary)
            setattr(func, DESCRIPTION_KEY, description)
            setattr(func, TAGS_KEY, tags)
            return func

        return decorator
