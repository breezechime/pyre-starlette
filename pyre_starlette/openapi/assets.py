"""OpenAPI 文档 UI 静态资源 CDN 地址（与 FastAPI 对齐，锁定版本）。"""

SWAGGER_UI_VERSION = "5.32.6"
REDOC_VERSION = "2.5.3"
RAPIDOC_VERSION = "9.3.8"

SWAGGER_UI_CSS_URL = (
    f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_UI_VERSION}/swagger-ui.css"
)
SWAGGER_UI_JS_URL = (
    f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_UI_VERSION}/swagger-ui-bundle.js"
)
REDOC_JS_URL = (
    f"https://cdn.jsdelivr.net/npm/redoc@{REDOC_VERSION}/bundles/redoc.standalone.js"
)
RAPIDOC_JS_URL = (
    f"https://cdn.jsdelivr.net/npm/rapidoc@{RAPIDOC_VERSION}/dist/rapidoc-min.js"
)
GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700"
)
SWAGGER_FAVICON_URL = "https://fastapi.tiangolo.com/img/favicon.png"
