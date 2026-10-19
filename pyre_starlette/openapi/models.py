from enum import Enum
from typing import Optional, Union, Dict, List, Annotated, Any, Literal, Set
from typing_extensions import TypedDict
from pydantic import BaseModel, ConfigDict, Field, AliasChoices
from pydantic.version import VERSION

PYDANTIC_V2 = VERSION.startswith("2.")


class BaseStructure(BaseModel):
    if PYDANTIC_V2:
        model_config = ConfigDict(extra="allow")
    else:
        class Config:
            extra = "allow"


class OpenAPI(BaseStructure):
    """
    OpenAPI 对象
    这是OpenAPI document的根文档对象。
    """

    """必选. 这个字符串必须是开放API规范版本号提到的符合语义化版本号规范的版本号。
    openapi字段应该被工具或者客户端用来解释 OpenAPI 文档。这个值和API info.version字符串没有关联。"""
    openapi: str

    """必选。此字段提供API相关的元数据。相关工具可能需要这个字段。"""
    info: "Info"

    """这是一个Server对象的数组，提供到服务器的连接信息。
    如果没有提供servers属性或者是一个空数组，那么默认为是url值为/的 Server 对象。"""
    servers: Optional[List["Server"]] = None

    """必选。对所提供的API有效的路径和操作。"""
    paths: Optional[Dict[str, Union["PathItem", Any]]] = None

    """一个包含多种结构的元素。"""
    components: Optional["Components"] = None

    """声明API使用的安全机制。The list of values includes alternative security requirement objects that can be used.
    认证一个请求时仅允许使用一种安全机制。单独的操作可以覆盖这里的定义。"""
    security: Optional[List[Dict[str, List[str]]]] = None

    """提供更多元数据的一系列标签，标签的顺序可以被转换工具用来决定API的顺序。
    不是所有被Operation 对象用到的标签都必须被声明。没有被声明的标签可能被工具按自己的逻辑任意整理，每个标签名都应该是唯一的。"""
    tags: Optional[List["Tag"]] = None

    """附加的文档。这个对象可能会被规范扩展扩展。"""
    external_docs: Optional["ExternalDocumentation"] = Field(default=None, serialization_alias="externalDocs")


class Contact(BaseStructure):
    """
    Contact 对象
    所公开的API的联系人信息
    Contact object
    Contact information for the exposed API
    """

    """人或组织的名称。
    The name of the person or organization."""
    name: Optional[str] = None

    """指向联系人信息的URL地址，必须是URL地址格式。
    URL pointing to the contact information. Must be in URL format."""
    url: Optional[str] = None

    """人或组织的email地址，必须是email地址格式。
    Email address of the person or organization. Must be in email address format."""
    email: Optional[str] = None


class License(BaseStructure):
    """
    License 对象
    所公开的API的许可证信息
    License object
    License information for the exposed API
    """

    """许可证的名称。
    The name of the license."""
    name: str

    """指向许可证信息的URL地址，必须是URL地址格式。
    URL pointing to the license information. Must be in URL format."""
    url: Optional[str] = None


class Info(BaseStructure):
    """
    Info 对象
    所公开的API的元数据
    Info object
    Metadata about the exposed API
    """

    title: Optional[str] = None

    """API的简要描述。
    A short description of the API."""
    summary: Optional[str] = None

    """API的详细描述。
    A longer description of the API."""
    description: Optional[str] = None

    """API的服务条款。
    The terms of service for the API."""
    terms_of_service: Optional[str] = Field(default=None, serialization_alias="termsOfService")

    """API的联系人信息。
    Contact information for the exposed API."""
    contact: Optional[Contact] = None

    """API的许可证信息。
    License information for the exposed API."""
    license: Optional[License] = None

    """API的版本号。
    The version of the API."""
    version: str


class ServerVariable(BaseStructure):
    """
    ServerVariable 对象
    服务器变量
    ServerVariable object
    Server variable for server URL
    """

    """服务器变量的枚举值。
    Enum values for server variable."""
    enum: Annotated[Optional[List[str]], Field(min_length=1)] = None

    """服务器变量的默认值。
    Default value for server variable."""
    default: str

    """服务器变量的描述。
    Description for server variable."""
    description: Optional[str] = None


class Server(BaseStructure):
    """
    Server 对象
    """

    """服务器URL。
    Server URL."""
    url: str

    """服务器描述。
    Server description."""
    description: Optional[str] = None

    """服务器变量。
    Server variables."""
    variables: Optional[Dict[str, ServerVariable]] = None


class Reference(BaseStructure):
    """
    Reference 对象
    """

    """引用对象的URL。
    URL of the referenced object."""
    ref: str = Field(alias="$ref")


class Tag(BaseStructure):
    """
    Tag 对象
    """

    """标签名称。
    Tag name."""
    name: str

    """标签描述。
    Tag description."""
    description: Optional[str] = None

    """外部文档。
    External documentation."""
    external_docs: Optional["ExternalDocumentation"] = Field(None, serialization_alias="externalDocs")


class Encoding(BaseStructure):
    contentType: Optional[str] = None
    headers: Optional[Dict[str, Union["Header", Reference]]] = None
    style: Optional[str] = None
    explode: Optional[bool] = None
    allowReserved: Optional[bool] = None


class Discriminator(BaseModel):
    """
    Discriminator 对象
    当一个 request bodies 或 response payloads 可以是多种 schemas 时，可以使用一个 discriminator 对象来帮助序列化、反序列化和校验。 The discriminator is a specific object in a schema which is used to inform the consumer of the specification of an alternative schema based on the value associated with it.
    当使用 discriminator 时，inline schemas 不会被考虑。
    """

    """必选. 在 payload 中表示 discriminator 值的属性的名称。"""
    property_name: str = Field(serialization_alias="propertyName")

    """一个映射 payload 中的值和 schema 名称或引用的对象。
    A mapping of payload values to the schema names or referenced schema objects."""
    mapping: Optional[Dict[str, str]] = None


class XML(BaseStructure):
    """
    XML 对象
    """

    """名称。
    Name."""
    name: Optional[str] = None

    """命名空间。
    Namespace."""
    namespace: Optional[str] = None

    """前缀。
    Prefix."""
    prefix: Optional[str] = None

    """属性。
    Attribute."""
    attribute: Optional[bool] = None

    """包装。
    Wrapped."""
    wrapped: Optional[bool] = None


class ExternalDocumentation(BaseStructure):
    """
    ExternalDocumentation 对象
    外部文档
    """

    """外部文档的描述。
    Description of the external documentation."""
    description: Optional[str] = None

    """URL。
    URL."""
    url: str


class Example(TypedDict, total=False):
    """
    Example 对象
    示例对象
    """

    """示例的摘要。
    Summary of the example."""
    summary: Optional[str]

    """示例的描述。
    Description of the example."""
    description: Optional[str]

    """示例的值。
    Value of the example."""
    value: Optional[Any]

    """外部示例的URL。
    URL of the external example."""
    externalValue: Optional[str]

    if PYDANTIC_V2:  # type: ignore [misc]
        __pydantic_config__ = {"extra": "allow"}

    else:
        class Config:
            extra = "allow"


class Schema(BaseStructure):
    # Ref: JSON Schema 2020-12: https://json-schema.org/draft/2020-12/json-schema-core.html#name-the-json-schema-core-vocabu
    # Core Vocabulary
    schema_: Optional[str] = Field(default=None, alias="$schema")
    vocabulary: Optional[str] = Field(default=None, alias="$vocabulary")
    id: Optional[str] = Field(default=None, alias="$id")
    anchor: Optional[str] = Field(default=None, alias="$anchor")
    dynamicAnchor: Optional[str] = Field(default=None, alias="$dynamicAnchor")
    ref: Optional[str] = Field(default=None, alias="$ref")
    dynamicRef: Optional[str] = Field(default=None, alias="$dynamicRef")
    defs: Optional[Dict[str, "SchemaOrBool"]] = Field(default=None, alias="$defs")
    comment: Optional[str] = Field(default=None, alias="$comment")
    # Ref: JSON Schema 2020-12: https://json-schema.org/draft/2020-12/json-schema-core.html#name-a-vocabulary-for-applying-s
    # A Vocabulary for Applying Subschemas
    allOf: Optional[List["SchemaOrBool"]] = None
    anyOf: Optional[List["SchemaOrBool"]] = None
    oneOf: Optional[List["SchemaOrBool"]] = None
    not_: Optional["SchemaOrBool"] = Field(default=None, alias="not")
    if_: Optional["SchemaOrBool"] = Field(default=None, alias="if")
    then: Optional["SchemaOrBool"] = None
    else_: Optional["SchemaOrBool"] = Field(default=None, alias="else")
    dependentSchemas: Optional[Dict[str, "SchemaOrBool"]] = None
    prefixItems: Optional[List["SchemaOrBool"]] = None
    # TODO: uncomment and remove below when deprecating Pydantic v1
    # It generales a list of schemas for tuples, before prefixItems was available
    # items: Optional["SchemaOrBool"] = None
    items: Optional[Union["SchemaOrBool", List["SchemaOrBool"]]] = None
    contains: Optional["SchemaOrBool"] = None
    properties: Optional[Dict[str, "SchemaOrBool"]] = None
    patternProperties: Optional[Dict[str, "SchemaOrBool"]] = None
    additionalProperties: Optional["SchemaOrBool"] = None
    propertyNames: Optional["SchemaOrBool"] = None
    unevaluatedItems: Optional["SchemaOrBool"] = None
    unevaluatedProperties: Optional["SchemaOrBool"] = None
    # Ref: JSON Schema Validation 2020-12: https://json-schema.org/draft/2020-12/json-schema-validation.html#name-a-vocabulary-for-structural
    # A Vocabulary for Structural Validation
    type: Optional[str] = None
    enum: Optional[List[Any]] = None
    const: Optional[Any] = None
    multipleOf: Optional[float] = Field(default=None, gt=0)
    maximum: Optional[float] = None
    exclusiveMaximum: Optional[float] = None
    minimum: Optional[float] = None
    exclusiveMinimum: Optional[float] = None
    maxLength: Optional[int] = Field(default=None, ge=0)
    minLength: Optional[int] = Field(default=None, ge=0)
    pattern: Optional[str] = None
    maxItems: Optional[int] = Field(default=None, ge=0)
    minItems: Optional[int] = Field(default=None, ge=0)
    uniqueItems: Optional[bool] = None
    maxContains: Optional[int] = Field(default=None, ge=0)
    minContains: Optional[int] = Field(default=None, ge=0)
    maxProperties: Optional[int] = Field(default=None, ge=0)
    minProperties: Optional[int] = Field(default=None, ge=0)
    required: Optional[List[str]] = None
    dependentRequired: Optional[Dict[str, Set[str]]] = None
    # Ref: JSON Schema Validation 2020-12: https://json-schema.org/draft/2020-12/json-schema-validation.html#name-vocabularies-for-semantic-c
    # Vocabularies for Semantic Content With "format"
    format: Optional[str] = None
    # Ref: JSON Schema Validation 2020-12: https://json-schema.org/draft/2020-12/json-schema-validation.html#name-a-vocabulary-for-the-conten
    # A Vocabulary for the Contents of String-Encoded Data
    contentEncoding: Optional[str] = None
    contentMediaType: Optional[str] = None
    contentSchema: Optional["SchemaOrBool"] = None
    # Ref: JSON Schema Validation 2020-12: https://json-schema.org/draft/2020-12/json-schema-validation.html#name-a-vocabulary-for-basic-meta
    # A Vocabulary for Basic Meta-Data Annotations
    title: Optional[str] = None
    description: Optional[str] = None
    default: Optional[Any] = None
    deprecated: Optional[bool] = None
    readOnly: Optional[bool] = None
    writeOnly: Optional[bool] = None
    examples: Optional[List[Any]] = None
    # Ref: OpenAPI 3.1.0: https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#schema-object
    # Schema Object
    discriminator: Optional[Discriminator] = None
    xml: Optional[XML] = None
    externalDocs: Optional[ExternalDocumentation] = None
    example: Optional[Any] = None


# Ref: https://json-schema.org/draft/2020-12/json-schema-core.html#name-json-schema-documents
# A JSON Schema MUST be an object or a boolean.
SchemaOrBool = Union[Schema, bool]


class MediaType(BaseStructure):
    schema_: Optional[Union[Schema, Reference]] = Field(default=None, alias="schema")
    example: Optional[Any] = None
    examples: Optional[Dict[str, Union[Example, Reference]]] = None
    encoding: Optional[Dict[str, Encoding]] = None


class RequestBody(BaseStructure):
    description: Optional[str] = None
    content: Dict[str, MediaType]
    required: Optional[bool] = None


class Link(BaseStructure):
    operationRef: Optional[str] = None
    operationId: Optional[str] = None
    parameters: Optional[Dict[str, Union[Any, str]]] = None
    requestBody: Optional[Union[Any, str]] = None
    description: Optional[str] = None
    server: Optional[Server] = None


class ParameterBase(BaseStructure):
    description: Optional[str] = None
    required: Optional[bool] = None
    deprecated: Optional[bool] = None
    # Serialization rules for simple scenarios
    style: Optional[str] = None
    explode: Optional[bool] = None
    allowReserved: Optional[bool] = None
    schema_: Optional[Union[Schema, Reference]] = Field(default=None, alias="schema")
    example: Optional[Any] = None
    examples: Optional[Dict[str, Union[Example, Reference]]] = None
    # Serialization rules for more complex scenarios
    content: Optional[Dict[str, MediaType]] = None


class ParameterInType(Enum):
    query = "query"
    header = "header"
    path = "path"
    cookie = "cookie"


class Parameter(ParameterBase):
    name: str
    in_: ParameterInType = Field(alias="in")


class Header(ParameterBase):
    pass


class Response(BaseStructure):
    description: str
    headers: Optional[Dict[str, Union[Header, Reference]]] = None
    content: Optional[Dict[str, MediaType]] = None
    links: Optional[Dict[str, Union[Link, Reference]]] = None


class Operation(BaseStructure):
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    # externalDocs: Optional[ExternalDocumentation] = None
    operation_id: Optional[str] = Field(default=None, validation_alias=AliasChoices('operation_id', 'operationId'),
                                        serialization_alias='operationId')
    parameters: Optional[List[Union[Parameter, Reference]]] = None

    request_body: Optional[Union[RequestBody, Reference]] = Field(
        default=None,
        validation_alias=AliasChoices("request_body", "requestBody"),
        serialization_alias='requestBody'
    )

    # Using Any for Specification Extensions
    responses: Optional[Dict[str, Union[Response, Any]]] = None
    callbacks: Optional[Dict[str, Union[Dict[str, "PathItem"], Reference]]] = None
    deprecated: Optional[bool] = None
    security: Optional[List[Dict[str, List[str]]]] = None
    servers: Optional[List[Server]] = None


class PathItem(BaseStructure):
    ref: Optional[str] = Field(default=None, alias="$ref")
    summary: Optional[str] = None
    description: Optional[str] = None
    get: Optional[Operation] = None
    put: Optional[Operation] = None
    post: Optional[Operation] = None
    delete: Optional[Operation] = None
    options: Optional[Operation] = None
    head: Optional[Operation] = None
    patch: Optional[Operation] = None
    trace: Optional[Operation] = None
    servers: Optional[List[Server]] = None
    parameters: Optional[List[Union[Parameter, Reference]]] = None


class Components(BaseStructure):
    schemas: Optional[Dict[str, Union[Schema, Reference]]] = None
    responses: Optional[Dict[str, Union[Response, Reference]]] = None
    parameters: Optional[Dict[str, Union[Parameter, Reference]]] = None
    examples: Optional[Dict[str, Union[Example, Reference]]] = None
    requestBodies: Optional[Dict[str, Union[RequestBody, Reference]]] = None
    headers: Optional[Dict[str, Union[Header, Reference]]] = None
    securitySchemes: Optional[Dict[str, Union["SecurityScheme", Reference]]] = None
    links: Optional[Dict[str, Union[Link, Reference]]] = None
    # Using Any for Specification Extensions
    callbacks: Optional[Dict[str, Union[Dict[str, PathItem], Reference, Any]]] = None
    pathItems: Optional[Dict[str, Union[PathItem, Reference]]] = None


class SecuritySchemeType(Enum):
    apiKey = "apiKey"
    http = "http"
    oauth2 = "oauth2"
    openIdConnect = "openIdConnect"


class SecurityBase(BaseStructure):
    type_: SecuritySchemeType = Field(alias="type")
    description: Optional[str] = None


class APIKeyIn(Enum):
    query = "query"
    header = "header"
    cookie = "cookie"


class APIKey(SecurityBase):
    type_: SecuritySchemeType = Field(default=SecuritySchemeType.apiKey, alias="type")
    in_: APIKeyIn = Field(alias="in")
    name: str


class HTTPBase(SecurityBase):
    type_: SecuritySchemeType = Field(default=SecuritySchemeType.http, alias="type")
    scheme: str


class HTTPBearer(HTTPBase):
    scheme: Literal["bearer"] = "bearer"
    bearerFormat: Optional[str] = None


class OAuthFlow(BaseStructure):
    refreshUrl: Optional[str] = None
    scopes: Dict[str, str] = {}


class OAuthFlowImplicit(OAuthFlow):
    authorizationUrl: str


class OAuthFlowPassword(OAuthFlow):
    tokenUrl: str


class OAuthFlowClientCredentials(OAuthFlow):
    tokenUrl: str


class OAuthFlowAuthorizationCode(OAuthFlow):
    authorizationUrl: str
    tokenUrl: str


class OAuthFlows(BaseStructure):
    implicit: Optional[OAuthFlowImplicit] = None
    password: Optional[OAuthFlowPassword] = None
    clientCredentials: Optional[OAuthFlowClientCredentials] = None
    authorizationCode: Optional[OAuthFlowAuthorizationCode] = None


class OAuth2(SecurityBase):
    type_: SecuritySchemeType = Field(default=SecuritySchemeType.oauth2, alias="type")
    flows: OAuthFlows


class OpenIdConnect(SecurityBase):
    type_: SecuritySchemeType = Field(
        default=SecuritySchemeType.openIdConnect, alias="type"
    )
    openIdConnectUrl: str


SecurityScheme = Union[APIKey, HTTPBase, OAuth2, OpenIdConnect, HTTPBearer]
