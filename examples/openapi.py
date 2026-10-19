"""OpenAPI 文档：声明式生成 spec，并暴露 Swagger / ReDoc / RapiDoc 三套 UI。

在仓库根目录执行：``python examples/openapi.py``
"""
import json
import logging
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _key in [key for key in os.environ if key.startswith(('SERVER_', 'PYRE_'))]:
    os.environ.pop(_key, None)

from pydantic import BaseModel, Field  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from pyre_starlette import (  # noqa: E402
    PyreStarlette,
    controller,
    route,
)
from pyre_starlette.config import AppConfig, OpenapiConfig, ServerConfig  # noqa: E402
from pyre_starlette.security import HTTPTokenAuth  # noqa: E402

app = PyreStarlette(
    app_config=AppConfig(server=ServerConfig(host="127.0.0.1", port=8123)),
    openapi_config=OpenapiConfig(
        enable=True,
        title='示例接口',
        version='1.0.0',
        description='pyre-starlette OpenAPI 示例',
        tags=['物品'],
        # 给文档页加一层 Basic Auth；去掉 username/password 即公开访问
        # username='admin', password='admin',
    ),
    notice=False,
)
logging.getLogger().setLevel(logging.ERROR)


class ListQuery(BaseModel):
    keyword: Optional[str] = Field(default=None, description='关键词')
    page: int = Field(default=1, description='页码')


class ItemBody(BaseModel):
    name: str = Field(description='名称')
    qty: int = Field(default=1, description='数量')


class ItemVo(BaseModel):
    id: int = Field(description='ID')
    name: str = Field(description='名称')
    qty: int = Field(description='数量')


# 带认证：spec 里会自动出现 securitySchemes，并把该接口标记为需要鉴权
auth = HTTPTokenAuth(security_name='BearerAuth', verify_token_callback=lambda token: {'id': 1})


@controller('/items', summary='物品', tags=['物品'], router=app.router)
class ItemController:
    @route('', methods=['GET'], summary='物品列表', query_model=ListQuery, response_model=List[ItemVo])
    def list_items(self, params: ListQuery):
        """按关键词分页查询。"""
        return [{'id': 1, 'name': params.keyword or 'demo', 'qty': 1}]

    @route('', methods=['POST'], summary='创建物品', body_model=ItemBody, response_model=ItemVo)
    def create_item(self, body: ItemBody):
        return {'id': 1, 'name': body.name, 'qty': body.qty}

    @route('/secure', methods=['GET'], summary='需要鉴权', response_model=ItemVo)
    @auth.login_required
    def secure(self):
        return {'id': 1, 'name': 'secret', 'qty': 1}


def main():
    spec = app.openapi.openapi()

    print('--- info ---')
    print(json.dumps(spec['info'], ensure_ascii=False, indent=2))

    print('\n--- servers ---')
    print(json.dumps(spec['servers'], ensure_ascii=False))

    print('\n--- tags ---')
    print(json.dumps(spec.get('tags', []), ensure_ascii=False))

    print('\n--- paths ---')
    for path, operations in spec['paths'].items():
        for method, op in operations.items():
            print(f'  {method.upper():6} {path:16} {op.get("summary", "")}')

    print('\n--- components.schemas ---')
    print(' ', sorted(spec['components'].get('schemas', {})))

    print('\n--- components.securitySchemes ---')
    print(' ', json.dumps(spec['components'].get('securitySchemes', {}), ensure_ascii=False))

    client = TestClient(app)
    print('\n--- 文档路由 ---')
    for url in ('/docs', '/redoc', '/openapi.json'):
        r = client.get(url)
        print(f'  {url:16} -> {r.status_code} {r.headers.get("content-type", "").split(";")[0]}')


if __name__ == '__main__':
    main()
