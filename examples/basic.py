"""最小可用示例：路由、控制器、参数注入与响应序列化。

在仓库根目录执行：``python examples/basic.py``
"""
import os
import sys
from typing import Annotated, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 为保证示例输出可复现，先清掉宿主机上的 SERVER_*/PYRE_* 变量。
for _key in [key for key in os.environ if key.startswith(('SERVER_', 'PYRE_'))]:
    os.environ.pop(_key, None)

from pydantic import BaseModel, Field  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from pyre_starlette import (  # noqa: E402
    Path,
    PyreStarlette,
    Query,
    Request,
    controller,
    route,
)

app = PyreStarlette(notice=False)

# pyre_starlette 的日志默认挂到 root，示例里顺手调静一点
import logging  # noqa: E402

logging.getLogger().setLevel(logging.ERROR)


# --------------------------------------------------------------------------- #
# 1. 函数式路由
# --------------------------------------------------------------------------- #

@app.router.get('/hello', summary='首页')
def hello(request: Request):
    return {'path': request.url.path, 'method': request.method}


@app.router.get('/health', summary='健康检查')
async def health():
    return {'status': 'ok'}


# --------------------------------------------------------------------------- #
# 2. 参数注入：Query / Path / Header
# --------------------------------------------------------------------------- #

class ItemQuery(BaseModel):
    """查询模型：字段名与查询串一一对应。"""

    keyword: Optional[str] = Field(default=None, description='关键词')
    page: int = Field(default=1, description='页码')
    size: int = Field(default=20, description='每页条数')


class ItemBody(BaseModel):
    """请求体模型：JSON 自动校验。"""

    name: str = Field(description='名称')
    qty: int = Field(default=1, description='数量')


# --------------------------------------------------------------------------- #
# 3. 控制器：按类聚合一组路由
# --------------------------------------------------------------------------- #

@controller('/items', summary='商品', tags=['商品'], router=app.router)
class ItemController:
    """控制器必须放在 ``@controller(prefix, router=...)`` 下，路由按定义顺序注册。"""

    @route('', methods=['GET'], summary='商品列表', query_model=ItemQuery)
    def list_items(self, params: ItemQuery):
        # query_model 会把整个查询串解析成 ItemQuery
        return {'keyword': params.keyword, 'page': params.page, 'size': params.size, 'items': []}

    @route('/search', methods=['GET'], summary='搜索')
    def search(self, keyword: Annotated[str, Query(description='关键词')], size: int = 10):
        # 路由按「定义顺序」注册，因此静态路由要写在参数路由之前，否则会被 /{item_id} 抢先匹配
        return {'keyword': keyword, 'size': size}

    @route('/{item_id}', methods=['GET'], summary='商品详情')
    def get_item(self, item_id: Annotated[int, Path(description='商品ID')]):
        return {'id': item_id, 'type': type(item_id).__name__}

    @route('', methods=['POST'], summary='创建商品', body_model=ItemBody, status_code=201)
    def create_item(self, body: ItemBody):
        return {'id': 1, 'name': body.name, 'qty': body.qty}


def main():
    client = TestClient(app)

    print('--- 函数式路由 ---')
    # 注意：框架已在 init_app 时把 `/` 注册为默认欢迎页，自定义根路由请先覆盖它
    print('GET  /        -> 欢迎页（框架内置，HTML）')
    print('GET  /hello   ->', client.get('/hello').json())
    print('GET  /health  ->', client.get('/health').json())

    print('\n--- 查询 / 路径 / 请求体 ---')
    print('GET  /items?keyword=book&page=2 ->', client.get('/items?keyword=book&page=2').json())
    print('GET  /items/42                   ->', client.get('/items/42').json())
    print('GET  /items/search?keyword=py    ->', client.get('/items/search?keyword=py').json())
    print('POST /items                      ->', client.post('/items', json={'name': 'book', 'qty': 3}).json())

    print('\n--- 参数校验失败 ---')
    bad = client.post('/items', json={})
    print('POST /items  (空 body) ->', bad.status_code, bad.json())

    print('\n--- 内置文档路由 ---')
    print('开放接口：', [r.path for r in app.router.iter_routes() if r.path in ('/docs', '/redoc', '/openapi.json')])


if __name__ == '__main__':
    main()
