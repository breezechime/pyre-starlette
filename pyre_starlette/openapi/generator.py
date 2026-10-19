from collections import defaultdict
from inspect import _empty, signature
from typing import Any, Dict, List, Union

from pydantic import BaseModel, TypeAdapter
from starlette.requests import Request

from ..params import (
    BodyInfo,
    CookieInfo,
    HeaderInfo,
    PathInfo,
    QueryInfo,
    resolve_annotated_param,
)
from ..routing import Route
from .models import (
    Components,
    Contact,
    HTTPBase,
    Info,
    License,
    MediaType,
    OpenAPI,
    Operation,
    Parameter,
    ParameterInType,
    PathItem,
    Reference,
    RequestBody,
    Response,
    Schema,
    SecuritySchemeType,
    Server,
    Tag,
)
from .utils import parse_convertor_schema, path_param_required

SUMMARY_KEY = "__pyre_openapi_summary__"
DESCRIPTION_KEY = "__pyre_openapi_description__"
TAGS_KEY = "__pyre_openapi_tags__"


class PyreStarletteOpenapiGenerator:
    """Pyre Starlette OpenAPI 生成器。"""

    def __init__(self, openapi_docs: Any):
        self.openapi_docs = openapi_docs
        self.adapters: Dict[Any, TypeAdapter] = {}
        self.schemas: Dict[Union[BaseModel, str], dict] = {}

    def generate(self) -> dict:
        path_items: Dict[str, PathItem] = defaultdict(PathItem)
        components = Components(schemas={}, securitySchemes={})

        for route in self.iter_routes():
            if not route.include_openapi:
                continue
            self.parse_openapi_path(route, route.func, path_items)

        for model_class, schema in self.schemas.items():
            if self._is_basemodel(model_class):
                schema_name = model_class.__name__
            else:
                schema_name = None
            if "$defs" in schema:
                for def_name, def_schema in schema.pop("$defs").items():
                    components.schemas[def_name] = Schema.model_validate(def_schema)
            if schema_name:
                components.schemas[schema_name] = Schema.model_validate(schema)

        for scheme_name, scheme_config in getattr(self.openapi_docs, 'security_schemes', {}).items():
            if scheme_config.get('type') == 'http':
                components.securitySchemes[scheme_name] = HTTPBase(
                    type_=SecuritySchemeType.http,
                    scheme=scheme_config.get('scheme', 'bearer').lower()
                )

        port = self.openapi_docs.pyre_app.app_config.server.port or 8000
        contact = self.openapi_docs.contact
        license_info = self.openapi_docs.license
        if isinstance(contact, dict):
            contact = Contact.model_validate(contact)
        if isinstance(license_info, dict):
            license_info = License.model_validate(license_info)

        servers = self.openapi_docs.servers
        if servers:
            servers = [
                Server.model_validate(item) if isinstance(item, dict) else item
                for item in servers
            ]
        else:
            servers = [Server(url=f"http://127.0.0.1:{port}")]

        tags = self.openapi_docs.tags
        if tags:
            tags = [
                Tag(name=item) if isinstance(item, str)
                else Tag.model_validate(item) if isinstance(item, dict)
                else item
                for item in tags
            ]

        openapi = OpenAPI(
            openapi=self.openapi_docs.openapi_version,
            info=Info(
                title=self.openapi_docs.title,
                version=self.openapi_docs.version,
                summary=self.openapi_docs.summary,
                description=self.openapi_docs.description,
                terms_of_service=self.openapi_docs.terms_of_service,
                contact=contact,
                license=license_info,
            ),
            servers=servers,
            paths=path_items,
            components=components,
            tags=tags,
        )
        result = openapi.model_dump(
            exclude_unset=True,
            exclude_none=True,
            by_alias=True,
            mode="json",
        )
        security_schemes = result.get('components', {}).get('securitySchemes', {})
        for scheme_name, scheme_config in security_schemes.items():
            if isinstance(scheme_config, dict) and 'type_' in scheme_config:
                scheme_config.pop('type_', None)
        return result

    def iter_routes(self) -> List[Route]:
        router = self.openapi_docs.pyre_app.router
        routes: List[Route] = []
        seen: set[int] = set()
        for route in router.iter_routes():
            if id(route) not in seen:
                routes.append(route)
                seen.add(id(route))
        return routes

    def parse_openapi_path(
        self,
        route: Route,
        func: Any,
        path_items: Dict[str, PathItem],
    ) -> None:
        summary = getattr(func, SUMMARY_KEY, route.summary)
        description = getattr(func, DESCRIPTION_KEY, route.description)
        tags = getattr(func, TAGS_KEY, route.tags)
        if isinstance(tags, str):
            tags = tags.split(",")

        for model in (
            route.query_model,
            route.body_model,
            route.header_model,
            route.cookie_model,
            route.response_model,
        ):
            if model and model not in self.schemas:
                self.schemas[model] = self._generate_schema(model)

        swagger_path, parameters = self.parse_openapi_parameters(route, func)
        request_body = self.parse_openapi_request_body(route)
        responses = self.parse_openapi_responses(route)

        auth_required = getattr(func, '__pyre_auth_required__', False)
        auth_scheme = getattr(func, '__pyre_auth_scheme__', 'Bearer')
        auth_name = getattr(func, '__pyre_auth_name__', 'BearerAuth')

        if auth_required and auth_name not in self.openapi_docs.security_schemes:
            self.openapi_docs.security_schemes[auth_name] = {
                "type": "http",
                "scheme": auth_scheme.lower(),
            }

        for method in route.methods or []:
            if method in {"HEAD", "OPTIONS"}:
                continue

            operation_id = f"{func.__name__}_{method.lower()}"
            endpoint_name = route.endpoint_name or route.name
            if endpoint_name:
                operation_id = f"{endpoint_name.replace('.', '_')}_{operation_id}"

            operation_kwargs: dict[str, Any] = {
                "summary": summary,
                "description": description,
                "operation_id": operation_id,
                "responses": responses,
            }
            if tags:
                operation_kwargs["tags"] = tags
            if parameters:
                operation_kwargs["parameters"] = parameters
            if request_body:
                operation_kwargs["request_body"] = request_body
            if auth_required:
                operation_kwargs["security"] = [{auth_name: []}]

            operation = Operation(**operation_kwargs)
            path_item = path_items[swagger_path]
            setattr(path_item, method.lower(), operation)

    def parse_other_parameters(
        self,
        schema: dict,
        param_type: ParameterInType = ParameterInType.query,
    ) -> List[Parameter]:
        """解析 query/header/cookie 参数并保留字段描述。"""
        parameters = []
        for key, prop in schema.get("properties", {}).items():
            description = prop.get("description") if isinstance(prop, dict) else None
            parameters.append(
                Parameter.model_validate(
                    {
                        "name": key,
                        "in": param_type,
                        "schema": prop,
                        "required": key in schema.get("required", []),
                        "description": description,
                    }
                )
            )
        return parameters

    def parse_openapi_parameters(self, route: Route, func: Any) -> tuple[str, List[Parameter]]:
        parameters: List[Parameter] = []
        func_params = signature(func).parameters
        swagger_path = getattr(route, "path_format", None) or route.path

        path_parameter_names: List[str] = []
        convertors = getattr(route, "param_convertors", None) or {}
        for name, convertor in convertors.items():
            path_parameter_names.append(name)
            func_param = func_params.get(name)
            annotation = func_param.annotation if func_param and func_param.annotation is not _empty else str
            _, meta = resolve_annotated_param(annotation)
            if meta and isinstance(meta, PathInfo):
                schema = self.get_type_adapter(annotation).json_schema()
            else:
                schema = parse_convertor_schema(convertor)
            parameters.append(
                Parameter.model_validate(
                    {
                        "name": name,
                        "in": ParameterInType.path,
                        "schema": schema,
                        "required": path_param_required(func_param),
                        "description": meta.description if meta else None,
                    }
                )
            )

        if route.query_model:
            parameters.extend(self.parse_other_parameters(self.schemas[route.query_model]))
        if route.header_model:
            parameters.extend(
                self.parse_other_parameters(
                    self.schemas[route.header_model],
                    ParameterInType.header,
                )
            )
        if route.cookie_model:
            parameters.extend(
                self.parse_other_parameters(
                    self.schemas[route.cookie_model],
                    ParameterInType.cookie,
                )
            )

        index = 0
        for key, func_param in func_params.items():
            if func_param.annotation is Request:
                continue
            if key in path_parameter_names:
                continue
            if index == 0 and not route.is_staticmethod:
                index += 1
                continue
            if func_param.annotation in {
                route.query_model,
                route.body_model,
                route.header_model,
                route.cookie_model,
            }:
                continue

            annotation = func_param.annotation if func_param.annotation is not _empty else Any
            _, meta = resolve_annotated_param(annotation)
            if meta and isinstance(meta, BodyInfo):
                continue

            param_type = ParameterInType.query
            if meta:
                if isinstance(meta, PathInfo):
                    param_type = ParameterInType.path
                elif isinstance(meta, HeaderInfo):
                    param_type = ParameterInType.header
                elif isinstance(meta, CookieInfo):
                    param_type = ParameterInType.cookie
                elif isinstance(meta, QueryInfo):
                    param_type = ParameterInType.query

            schema = self.get_type_adapter(annotation).json_schema()
            parameters.append(
                Parameter.model_validate(
                    {
                        "name": key,
                        "in": param_type,
                        "schema": schema,
                        "required": func_param.default is _empty,
                        "description": meta.description if meta else None,
                    }
                )
            )
            index += 1

        return swagger_path, parameters

    def get_type_adapter(self, typer: Any) -> TypeAdapter:
        if typer not in self.adapters:
            self.adapters[typer] = TypeAdapter(typer)
        return self.adapters[typer]

    def _is_basemodel(self, model: Any) -> bool:
        """判断是否是 BaseModel 子类"""
        return isinstance(model, type) and issubclass(model, BaseModel)

    def _generate_schema(self, model: Any) -> dict:
        """生成 model 的 json schema，BaseModel 子类用 model_json_schema，typing 泛型用 TypeAdapter"""
        ref_template = "#/components/schemas/{model}"
        if self._is_basemodel(model):
            return model.model_json_schema(ref_template=ref_template)
        return self.get_type_adapter(model).json_schema(ref_template=ref_template)

    def _get_schema_ref(self, model: Any) -> Any:
        """获取 schema 引用：BaseModel 用 $ref，typing 泛型用内联 schema（$defs 已提取到 components）"""
        if self._is_basemodel(model):
            return Reference.model_validate(
                {"$ref": f"#/components/schemas/{model.__name__}"}
            )
        if model not in self.schemas:
            self.schemas[model] = self._generate_schema(model)
        schema = self.schemas[model]
        inline = {k: v for k, v in schema.items() if k != "$defs"}
        return Schema.model_validate(inline)

    def parse_openapi_responses(self, route: Route) -> dict[str, Response]:
        """解析接口响应模型并合并路由自定义响应。"""
        if route.response_model:
            responses = {
                str(route.status_code or 200): Response(
                    description=route.response_description,
                    content={
                        "application/json": MediaType(
                            schema=self._get_schema_ref(route.response_model)
                        )
                    },
                ),
            }
        else:
            responses = {
                str(route.status_code or 200): Response(
                    description=route.response_description or "Successful Response",
                )
            }

        for status_code, route_response in (route.responses or {}).items():
            if isinstance(route_response, Response):
                responses[str(status_code)] = route_response
                continue
            response_config = dict(route_response)
            response_model = response_config.pop("model", None)
            if response_model and "content" not in response_config:
                response_config["content"] = {
                    "application/json": MediaType(schema=self._get_schema_ref(response_model))
                }
            response_config.setdefault("description", route.response_description or "Response")
            responses[str(status_code)] = Response.model_validate(response_config)
        return responses

    def parse_openapi_request_body(self, route: Route) -> RequestBody | None:
        """解析接口请求体。"""
        openapi_request_body = route.options.get("openapi_request_body")
        if openapi_request_body:
            return RequestBody.model_validate(openapi_request_body)
        if not route.body_model:
            return None
        return RequestBody(
            content={
                "application/json": MediaType(
                    schema=self._get_schema_ref(route.body_model)
                )
            }
        )
