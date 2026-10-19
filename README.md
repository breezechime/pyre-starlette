# pyre-starlette

基于 [Starlette](https://www.starlette.dev/) 的异步 Web 框架：**控制器路由、参数注入、依赖注入、
统一响应、OpenAPI 文档与代码生成**。

复用 [pyre-config](https://github.com/breezechime/pyre-config)（配置）、
[pyre-injector](https://github.com/breezechime/pyre-injector)（依赖注入）、
[sqlalchemy-db](https://github.com/breezechime/sqlalchemy-db)（ORM 增强），
把「写接口」压缩成声明式的注解。

```python
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from pyre_starlette import PyreStarlette, controller, route, Query

app = PyreStarlette(notice=False)


class ItemBody(BaseModel):
    name: str = Field(description='名称')
    qty: int = Field(default=1, description='数量')


@controller('/items', summary='商品', tags=['商品'], router=app.router)
class ItemController:
    @route('', methods=['GET'], summary='列表')
    def list_items(self, keyword: Annotated[Optional[str], Query(description='关键词')] = None):
        return {'keyword': keyword, 'items': []}

    @route('', methods=['POST'], summary='创建', body_model=ItemBody, status_code=201)
    def create(self, body: ItemBody):
        return {'id': 1, 'name': body.name, 'qty': body.qty}
```

```bash
$ uvicorn app:app
INFO:  Uvicorn running on http://127.0.0.1:8000
```

访问 `/docs` 即可拿到自动生成的 Swagger UI。

## 特性

- **两种路由写法** — 函数式 `@app.router.get(...)` 与控制器式 `@controller(...)` + `@route(...)`。
- **按定义顺序注册** — 控制器内的路由严格按代码书写顺序注册，静态路由不会被参数路由抢先匹配。
- **参数注入** — `Query` / `Body` / `Path` / `Header` / `Cookie` 五种来源，支持单参数、`Annotated` 与
  Pydantic 模型（`query_model` / `body_model` / `header_model` / `cookie_model`）。
- **响应模型校验** — `response_model` 自动校验与序列化，支持 `List[...]`、标量、泛型与 `by_alias` 控制。
- **统一异常体系** — `ApplicationException` 家族（400/401/403/404/405/415/419/500…），错误消息可注册与本地化。
- **依赖注入** — 直接复用 pyre-injector：控制器构造注入、`provider()` / `autowired()` 手动取用、`BaseService` 自动注册。
- **配置驱动** — 复用 pyre-config：多源、多环境、环境变量与命令行覆盖，配置即 `AppConfig` 模型。
- **数据库集成** — 复用 sqlalchemy-db：自动建引擎、请求级事务中间件、`models.Model` 声明式模型。
- **OpenAPI 3.0** — 从路由元数据自动生成 spec，内置 Swagger / ReDoc / RapiDoc 三套 UI，可选 Basic Auth 保护。
- **请求上下文** — `get_request()` / `try_get_request()` 在任意位置取当前请求。
- **后台任务** — `app.add_background_task()` 自动适配 sync/async 与调用上下文，支持错误回调。
- **事件总线** — `event.listen` / `event.emit` 解耦模块间通信。
- **CLI 与代码生成** — `pyre new / run / make / list / eject / doctor`，可生成空壳、按内联字段、反射已有表或解析已有模型，并支持模型到 schema 的增量同步。

## 安装

```bash
pip install pyre-starlette
```

`pyre-config`、`pyre-injector`、`sqlalchemy-db` 会作为依赖自动安装。

按需安装可选能力：

```bash
pip install "pyre-starlette[cli]"        # uvicorn，用于 pyre run / app.run()
pip install "pyre-starlette[auth]"       # authlib + werkzeug，JWT 与密码哈希
pip install "pyre-starlette[redis]"      # redis
pip install "pyre-starlette[scheduler]"  # apscheduler 定时任务
pip install "pyre-starlette[async]"      # greenlet + aiosqlite，异步数据库
pip install "pyre-starlette[all]"
```

`Jinja2`、`colorlog`、`pydantic>=2`、`starlette>=1.0` 为核心依赖。
Flask 仅在使用 `PyreJSONProvider` 时才需要，缺失不影响框架启动。

## 快速开始

### 目录约定

```
project/
├── app.py
├── apps/                     # 业务应用
│   └── system/
│       └── user/
│           ├── controller.py
│           ├── service.py
│           └── models.py
└── resource/                 # 配置
    ├── application.toml
    └── application-dev.toml
```

### app.py

```python
from pyre_starlette import PyreStarlette, Router

app = PyreStarlette()

api_router = Router()
# 业务控制器在 import 时用 @controller(..., router=api_router) 挂载
from apps.system.user import controller  # noqa: F401,E402

app.add_router(api_router, prefix='/api')

if __name__ == '__main__':
    app.run()
```

### resource/application.toml

```toml
[pyre.config]
env = 'dev'

[server]
host = '0.0.0.0'
port = 8000
```

### resource/application-dev.toml

```toml
[pyre.datasource]
url = 'mysql+pymysql://root:root@127.0.0.1:3306/demo?charset=utf8mb4'

[pyre.application]
secret_key = 'change-me'
```

启动：

```bash
python app.py
# 或
pyre run --host 0.0.0.0 --port 8000
```

## 应用与配置

### PyreStarlette 构造参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `app_config` | `None` | `AppConfig` 实例或字典，作为最低优先级的配置默认值 |
| `openapi_config` | `None` | `OpenapiConfig` 实例或字典，覆盖 `pyre.openapi` 段 |
| `config_loader` | `ConfigLoader()` | 自定义配置加载器 |
| `init_app` | `True` | 为 `False` 时只构造对象，稍后手动调用 `init_app()` |
| `include_openapi` | `True` | 是否注册 `/openapi.json` 等文档路由 |
| `notice` | `True` | 是否在启动时输出 NOTICE 日志（含艺术字） |
| `debug` / `routes` / `middleware` / `lifespan` / `redirect_slashes` | 同 Starlette | 透传给底层 Starlette |

`init_app()` 完成的事情：加载配置 → 重建环境对象 → 重配日志 → 注入容器 → 初始化数据库 / Redis /
调度器 / OpenAPI → 注册默认首页 `/`。

### 配置优先级

由 pyre-config 提供，从低到高：

| 顺序 | 来源 |
| --- | --- |
| 1 | `PyreStarlette(app_config=...)` 传入的默认值 |
| 2 | `resource/application.toml`（基础配置） |
| 3 | `resource/application-dev.toml`（环境配置） |
| 4 | 环境变量 `SERVER_*` / `PYRE_*` |
| 5 | 命令行参数 `--server.port 9000` |

```python
app.app_config.server.port              # 8000
app.app_config.pyre.datasource.url      # 数据源 URL
app.app_config.pyre.config.envs         # 实际生效的环境链
app.environment.is_dev()                # True
```

自定义配置位置：

```python
app = PyreStarlette(config_loader=ConfigLoader())
app.config_loader.scanner.config_locations = ['./conf']
```

### 类型化配置

```python
from pydantic import BaseModel
from pyre_starlette import AppConfig, PyreConfig, ServerConfig

app = PyreStarlette(app_config=AppConfig(
    server=ServerConfig(host='127.0.0.1', port=8000),
    pyre=PyreConfig(locale='zh-hans'),
))
```

## 路由

### 函数式

```python
@app.router.get('/users', summary='用户列表')
def list_users(page: int = 1):
    return {'page': page}


@app.router.get('/users/{user_id:int}', summary='用户详情')
def get_user(user_id: int):
    return {'id': user_id}


@app.router.post('/users', summary='创建用户', status_code=201)
async def create_user(body: CreateBody):
    return {'id': 1}
```

可用方法：`get` / `post` / `put` / `delete` / `patch` / `head` / `options` / `route`（自定义方法集合）。

路径转换器：`:int`、`:float`、`:path`、`:uuid` 等（同 Starlette）。不匹配时该路由不参与匹配。

### Router 与前缀

```python
from pyre_starlette import Router

leaf = Router(prefix='/leaf')

@leaf.get('/ping')
def ping():
    return {'pong': True}

middle = Router(prefix='/middle')
middle.add_router(leaf, prefix='/inner')

app.add_router(middle, prefix='/outer')
# 最终路径：/outer/middle/inner/leaf/ping
```

嵌套时每一层 router 自身的 `prefix` 都会保留，`add_router(prefix=...)` 只是在外层再叠一层。

### 控制器

`@controller(rule, router=...)` 把一组方法挂到同一个前缀下，方法用 `@route` 声明。

```python
from typing import Annotated
from pyre_starlette import controller, route, Path, Query


@controller('/orders', summary='订单', tags=['订单'], router=app.router)
class OrderController:
    def __init__(self, service: OrderService):     # 由容器注入
        self.service = service

    @route('/search', methods=['GET'], summary='搜索')      # 静态路由写在前面
    def search(self, keyword: Annotated[str, Query(description='关键词')]):
        return self.service.search(keyword)

    @route('/{order_id}', methods=['GET'], summary='详情')   # 参数路由写在后面
    def detail(self, order_id: Annotated[int, Path(description='订单ID')]):
        return self.service.get(order_id)
```

要点：

- **路由按定义顺序注册**。需要「静态优先」时把静态路由写在参数路由之前。
- 控制器方法**不必**继承 `Controller`。只有需要 `before_request` / `after_request` / `middlewares` 时才继承。
- 子类控制器的路由会与父类合并，子类同名方法覆盖父类。
- 控制器类会在挂载时自动注册进 DI 容器，构造参数按类型注解注入。

继承 `Controller` 扩展请求钩子：

```python
from pyre_starlette import Controller, controller, route


@controller('/admin', router=app.router)
class AdminController(Controller):
    def before_request(self, **kwargs):
        ...           # 每个请求前

    def after_request(self, response):
        return response  # 每个请求后

    @route('/ping', methods=['GET'])
    def ping(self):
        return {'ok': self.autowired(SomeService) is not None}
```

### 路由元数据

`summary` / `description` / `tags` / `include_openapi` / `include_operation_log` 既可写在
`@route` 上，也可写在 `@controller` 上作为整组的默认值。这些元数据会进入 OpenAPI spec。

## 参数注入

函数参数按顺序依次从**路径 → 查询 → 请求头 → Cookie → 请求体**中解析（`query_model` /
`body_model` 等显式模型参数优先）。

### 单参数

```python
@app.router.get('/list')
def listing(
    keyword: str,                    # 必填查询参数，缺失 → 400
    page: int = 1,                   # 带默认值，缺失时用默认值
    size: int = 20,
    flag: bool = False,
    x_token: str | None = None,      # 可选
):
    return {'keyword': keyword, 'page': page, 'size': size, 'flag': flag}
```

### Annotated 声明

```python
from typing import Annotated, Optional
from pyre_starlette import Body, Cookie, Header, Path, Query


@app.router.get('/annotated/{item_id}')
def annotated(
    item_id: Annotated[int, Path(description='ID')],
    keyword: Annotated[str, Query(description='关键词')],
    page: Annotated[int, Query(default=1, description='页码')] = 1,
    x_token: Annotated[Optional[str], Header()] = None,
    sid: Annotated[Optional[str], Cookie()] = None,
):
    ...
```

`Annotated[..., Query(default=...)]` 上的默认值优先于函数签名默认值。

### 模型参数

```python
from pydantic import BaseModel, Field


class ListQuery(BaseModel):
    keyword: str | None = Field(default=None, description='关键词')
    page: int = Field(default=1, description='页码')


class CreateBody(BaseModel):
    name: str = Field(description='名称')
    qty: int = Field(default=1, description='数量')


@app.router.route('/items', methods=['GET'], query_model=ListQuery)
def list_items(params: ListQuery):
    return {'keyword': params.keyword, 'page': params.page}


@app.router.route('/items', methods=['POST'], body_model=CreateBody)
def create_item(body: CreateBody):
    return {'name': body.name, 'qty': body.qty}
```

同理可用 `header_model` / `cookie_model`；`Annotated[Model, Body()]` 也可直接标注请求体。

### 注入 Request

```python
from pyre_starlette import Request


@app.router.get('/whoami')
def whoami(request: Request, page: int = 1):
    return {'method': request.method, 'path': request.url.path, 'page': page}
```

### 校验失败

参数校验失败统一返回 400，消息形如：

```json
{"code": 400, "msg": "请求参数校验错误, 字段 'name' 必填项"}
```

## 响应与序列化

### 返回值

| 返回类型 | 行为 |
| --- | --- |
| `dict` / `list` / 标量 | `jsonable_encoder` 序列化后以 JSON 返回 |
| Pydantic `BaseModel` | `model_dump(mode='json')` 后返回 |
| `Response` 及子类 | 原样透传，不做任何处理 |

```python
from pyre_starlette import Response, PlainTextResponse


@app.router.get('/raw')
def raw():
    return PlainTextResponse('hello', status_code=201)
```

### response_model

```python
from typing import List
from pydantic import BaseModel


class ItemVo(BaseModel):
    id: int
    name: str


@app.router.route('/items', methods=['GET'], response_model=List[ItemVo])
def list_items():
    return [{'id': 1, 'name': 'a'}]
```

- 仅在状态码为 200（或未指定）时执行校验，`status_code=201` 等场景跳过。
- 校验失败返回 500。
- 支持 `response_model_include` / `response_model_exclude` / `response_model_by_alias` /
  `response_model_exclude_unset` / `response_model_exclude_defaults` 等序列化控制。
- 响应为 SQLAlchemy 模型等非 Pydantic 对象时，会先编码为纯字典再校验。

### jsonable_encoder

```python
from pyre_starlette import jsonable_encoder

jsonable_encoder({'dt': datetime.datetime(2026, 1, 2, 3, 4, 5)})
# {'dt': '2026-01-02 03:04:05'}
```

支持 `datetime` / `date` / `Enum` / `set` / 嵌套模型；对**循环引用**返回 `None`，
并以 `ContextVar` 保存递归状态，多线程并发调用互不干扰。

### 统一响应封装

框架只负责把返回值序列化成 JSON。「`code` / `msg` / `data`」这类业务信封由应用层自行定义
（框架不强制，也不内置）。典型做法是在 `common/response/response.py` 里写一个 `ResultResponse`
模型与 `response()` 工厂，然后在接口里返回它：

```python
from common.response import response


@app.router.get('/items')
def list_items():
    return response(data=[{'id': 1}], total=1)
```

## 异常与错误处理

### 异常体系

```python
from pyre_starlette.exceptions import (
    BadRequestException,        # 400
    UnauthorizedException,      # 401
    ForbiddenException,         # 403
    NotFoundException,          # 404
    NotFoundDataException,      # 404（查无数据）
    MethodNotAllowException,    # 405
    UnsupportedMediaTypeException,  # 415
    AuthenticationTimeoutException, # 419
    ApplicationException,       # 基类，默认 500
)


@app.router.get('/x')
def x(flag: bool = False):
    if flag:
        raise NotFoundDataException(detail='不存在')
    raise BadRequestException()
```

所有 `ApplicationException` 子类都会返回统一信封：

```json
{"code": 404, "msg": "Not Found Data"}
```

可传 `msg` 覆盖消息、`code` 覆盖业务码、`status_code` 覆盖 HTTP 状态码。

### 自定义处理器

```python
from pyre_starlette import Response


@app.exception_handler(MyException)
def handle_my_exception(request, exc):
    return Response({'code': 500, 'msg': str(exc)}, status_code=500)
```

也可以直接返回 `Response` 实例或 payload 字典。

### 消息本地化

```python
from pyre_starlette.exceptions import register_messages

register_messages({'Not Found Data': '数据不存在'})
```

未捕获异常统一返回 500，并由 `logger.error` 记录堆栈。

## 依赖注入

框架内置的 `PyreStarlette` / `AppConfig` / `Environment` / `PyreLogger` / `SQLAlchemyDB` /
`State` / `OpenAPI` 等对象在 `init_app()` 时已注入容器。

```python
from pyre_starlette import provider, BaseService, controller, route


class Repository:
    def find(self, key: str) -> str | None:
        ...
```

```python
app.dependency_container.inject(Repository)     # 注册普通类
```

```python
@controller('/svc', router=app.router)
class SvcController:
    def __init__(self, repo: Repository):       # 构造注入
        self.repo = repo

    @route('/{key}', methods=['GET'])
    def get(self, key: str):
        return {'value': provider(Repository).find(key)}   # 手动取用
```

**依赖必须先注册后使用**：`BaseService` 子类在**类定义时**就会解析构造参数，
因此其依赖要在这之前 `inject`。缺失依赖时会抛出带**文件与行号**的明确错误：

```
DependencyNotRegisteredError: Dependency 'Repository' is not registered, but it is
required by parameter 'repo' of CatalogService (examples/dependency_injection.py:36).
```

### BaseService

```python
from pyre_starlette import BaseService


class OrderService(BaseService):
    model_class = Order        # 继承后自动注册进容器，无需手动 inject

    def search(self, keyword: str):
        filters = self.service_filter({'name': keyword})   # 条件构建
        order_by = self.service_order_by(order_by='created_at', sort='desc')
        return self.model_class.query.filter(*filters).order_by(order_by).all()
```

常用工具方法：`service_general_save` / `service_filter` / `service_order_by` / `provider` /
`add_background_task`。

## 中间件与请求上下文

`RequestContextMiddleware` 永远是**第一个**中间件，它把当前 `Request` 绑定到 `ContextVar`：

```python
from pyre_starlette import get_request, try_get_request, with_request_context


@app.router.get('/ctx')
def ctx():
    request = get_request()          # 无上下文时抛 RuntimeError
    return {'path': request.url.path, 'has': try_get_request() is not None}
```

给非 endpoint 函数绑定上下文：

```python
@app.router.get('/wrapped')
@with_request_context
async def wrapped(request: Request):
    return {'path': get_request().url.path}
```

自定义中间件：

```python
from pyre_starlette import Middleware


@app.middleware()
async def timing(request, call_next):
    response = await call_next(request)
    response.headers['X-Trace'] = 'abc'
    return response
```

`app.add_middleware(...)` 会把新中间件插到 `RequestContextMiddleware` 之后，保证顺序可控。

CORS：

```python
from pyre_starlette.middleware import CORSMiddleware

app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
```

## 后台任务

```python
@app.router.get('/notify')
async def notify():
    app.add_background_task(send_mail, 'a@b.com', on_error=lambda e: print(e))
    return {'ok': True}
```

- 与当前请求**并发**执行，不阻塞响应。
- sync 函数走线程池，async 函数在事件循环中 `create_task`。
- 返回 `asyncio.Task` 或 `concurrent.futures.Future`，可 `cancel()` / `add_done_callback()`。
- 异常自动 `logger.error`，并触发 `on_error` 回调。

需要「响应发送完成后再执行」时，用 Starlette 的 `BackgroundTasks`：

```python
from pyre_starlette import BackgroundTasks


@app.router.get('/cleanup')
def cleanup():
    tasks = BackgroundTasks()
    tasks.add_task(remove_file, path)
    return Response({'ok': True}, background=tasks)
```

## 事件

```python
from pyre_starlette import event, Event


@event.listen('user.created')
def on_user_created(data):
    ...


event.emit('user.created', {'id': 1})
event.emit(Event('user.created', {'id': 1}))
```

监听函数按参数个数自动适配：0 个参数收到空调用、1 个参数收到 `data`、2 个及以上收到 `(name, data)`。

## 安全

```python
from pyre_starlette.security import HTTPBasicAuth, HTTPTokenAuth, HTTPApiKeyAuth

auth = HTTPTokenAuth(security_name='BearerAuth', verify_token_callback=lambda t: {'id': 1})


@app.router.get('/me')
@auth.login_required
def me():
    return {'id': 1}


@app.router.get('/admin')
@auth.login_required(role='admin')
def admin():
    return {'ok': True}
```

| 类 | 说明 |
| --- | --- |
| `HTTPBasicAuth` | HTTP Basic |
| `HTTPDigestAuth` | HTTP Digest |
| `HTTPTokenAuth` | Bearer Token |
| `HTTPApiKeyAuth` | API Key（header 或 query） |

认证失败返回 401 并带 `WWW-Authenticate`；角色不足或 `authorize()` 返回 `False` 返回 403。
被 `login_required` 保护的接口会自动写入 OpenAPI 的 `securitySchemes`。

## 数据库

`pyre.datasource` 存在时，`init_app()` 会自动建引擎、注入 `SQLAlchemyDB` 并挂上
`DatabaseMiddleware`（请求级事务）。

```python
from pyre_starlette import models


class Note(models.Model, models.PkMixin, models.TimestampMixin):
    __tablename__ = 'note'
    __table_args__ = {'comment': '便签'}

    title = models.StringField(128, nullable=False, comment='标题')


app.db.create_all()


@app.router.post('/notes')
def add(title: str):
    note = Note(title=title)
    note.save()
    return {'id': note.id}


@app.router.get('/notes')
def list_notes():
    return {'count': Note.query.count()}
```

注入 `SQLAlchemyDB` 使用事务：

```python
from pyre_starlette import SQLAlchemyDB, transactional


@transactional
def do_something(db: SQLAlchemyDB):
    ...
```

也可通过 `autowired(SQLAlchemyDB)` 或 `provider(SQLAlchemyDB)` 取用。

## 日志

基于 `colorlog`，控制台带颜色、文件为纯文本，并提供**线程级日志收集器**
（非主线程写入的日志可在同一线程内取出，适合把任务日志回传给接口调用方）。

```toml
[logging]
name = 'myapp'
level = 20
file_path = 'logs/app.log'
thread_log_max_entries = 500
thread_log_max_chars = 65536

[[logging.loggers]]
name = 'myapp.sql'
level = 10
```

```python
app.logger.notice('自定义级别日志')
app.logging.thread_log_handler.get_log_data()    # 当前线程已收集的日志文本
```

`NOTICE` 是框架注册的额外日志级别（数值 28），介于 INFO 与 WARNING 之间。

## OpenAPI 文档

```python
from pyre_starlette import PyreStarlette
from pyre_starlette.config import OpenapiConfig

app = PyreStarlette(openapi_config=OpenapiConfig(
    enable=True,
    title='示例接口',
    version='1.0.0',
    description='pyre-starlette 示例',
    tags=['物品'],
    ui='swagger',            # swagger | redoc | rapidoc
    # username='admin', password='admin',   # 开启后文档页需要 Basic Auth
))
```

| 路由 | 说明 |
| --- | --- |
| `/openapi.json` | OpenAPI 3.0 spec |
| `/docs` | 文档页，`?ui=redoc` / `?ui=rapidoc` 可切换 UI |
| `/redoc` | 直接渲染 ReDoc |

spec 内容来自路由元数据（`summary` / `description` / `tags`）、参数模型、请求体模型、
`response_model`、安全方案与 `servers`。也可以用一个独立装饰器在函数上补充元数据：

```python
from pyre_starlette.openapi import PyreStarletteOpenapi


@PyreStarletteOpenapi().doc(summary='摘要', description='描述', tags=['物品'])
def handler():
    ...
```

不需要文档时：`PyreStarlette(include_openapi=False)`，或 `OpenapiConfig(enable=False)`
（后者会同时移除文档路由并把 `app.openapi` 置为 `None`）。

## CLI

安装 `pyre-starlette[cli]` 后可用 `pyre` 命令：

```bash
pyre new myproject                     # 生成项目骨架（别名 n / init / i）
pyre run --host 0.0.0.0 --port 8000    # 启动服务（别名 r）
pyre doctor                            # 项目自检（别名 d）

pyre make module article -a content    # 整套模块（6 个文件，推荐）
pyre c article -a content              # 顶层快捷命令 ≡ pyre make c
pyre m article -f "id:bigint!@#,title:str:128!#标题"   # 内联字段
pyre crud system_area -a system        # 按已有表反射生成整套 CRUD
pyre sy -m apps/content/article/models.py              # 模型 → schema 增量同步

pyre list                              # 生成类型与内置模板
pyre eject module/models.py            # 导出模板到项目 templates/ 后即可覆盖
```

`<kind>` 可以直接写在 `make` 后面，也可以作为顶层命令，两者等价。生成来源按
`-t/--table` → `-m/--from-model` → `-f/--fields` → 空壳 的优先级决定；
`-n/--dry-run` 预览、`-v/--verbose` 打印内容、`-R/--register` 自动写入
`apps/__init__.py` 注册表。详见 [pyre-docs](https://github.com/breezechime/pyre-starlette)。

## API 参考

| 名称 | 说明 |
| --- | --- |
| `PyreStarlette` | 应用类。`init_app` / `add_router` / `controller` / `run` / `add_background_task` / `exception_handler` / `add_middleware` |
| `Router` / `Route` | 路由器与路由。`route` / `get` / `post` / `put` / `delete` / `patch` / `head` / `options` / `controller` / `add_router` / `get_route` / `iter_routes` |
| `controller` / `route` / `get` / `post` / `put` / `delete` / `patch` / `head` / `options` | 控制器与路由装饰器 |
| `Controller` | 控制器 Mixin（可选继承，用于 `before_request` / `after_request`） |
| `Query` / `Body` / `Path` / `Header` / `Cookie` + `*Info` / `ParamTypes` | 参数声明 |
| `Response` / `jsonable_encoder` | 响应与序列化 |
| `ApplicationException` 家族 / `register_messages` | 异常与消息注册 |
| `BaseService` / `provider` / `inject` / `autowired` | 依赖注入（来自 pyre-injector） |
| `SQLAlchemyDB` / `transactional` / `Page` / `IPage` / `Propagation` / `Isolation` | 数据库（来自 sqlalchemy-db） |
| `models.Model` / `models.PkMixin` / `models.TimestampMixin` | 声明式模型基类 |
| `AppConfig` / `PyreConfig` / `ServerConfig` / `OpenapiConfig` / `LoggingConfig` | 配置模型 |
| `Environment` | 环境对象。`is_dev()` / `is_prod()` / `get_env_strings()` |
| `get_request` / `try_get_request` / `with_request_context` | 请求上下文 |
| `Event` / `event` | 事件总线 |
| `HTTPBasicAuth` / `HTTPDigestAuth` / `HTTPTokenAuth` / `HTTPApiKeyAuth` | 认证 |
| `PyreStarletteOpenapi` / `PyreStarletteOpenapiGenerator` | OpenAPI 文档与生成器 |
| `Middleware` / `CORSMiddleware` / `BaseHTTPMiddleware` | 中间件 |

## 开发

```bash
pip install -e ".[all]" pytest httpx
pytest tests -q
```

示例：

```bash
python examples/basic.py               # 路由、参数注入、响应
python examples/dependency_injection.py  # 依赖注入与 BaseService
python examples/config_and_database.py   # 配置加载与 SQLite CRUD
python examples/openapi.py               # OpenAPI 与文档路由
```

## 许可

本项目基于 [MIT](LICENSE) 许可开源。
