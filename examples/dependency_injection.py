"""依赖注入：控制器构造注入、`provider` 手动取用、`BaseService` 业务基类。

在仓库根目录执行：``python examples/dependency_injection.py``
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _key in [key for key in os.environ if key.startswith(('SERVER_', 'PYRE_'))]:
    os.environ.pop(_key, None)

from starlette.testclient import TestClient  # noqa: E402

from pyre_starlette import BaseService, PyreStarlette, controller, provider, route  # noqa: E402

app = PyreStarlette(notice=False)
logging.getLogger().setLevel(logging.ERROR)


# --------------------------------------------------------------------------- #
# 1. 普通依赖：任何类都可以被容器接管，构造参数按类型注解自动注入
# --------------------------------------------------------------------------- #

class Repository:
    """数据仓库（示例里用内存字典代替）。"""

    def __init__(self):
        self.data = {'1': 'one', '2': 'two'}

    def find(self, key: str):
        return self.data.get(key)


# 手动注册普通类。依赖必须「先注册、后使用」：BaseService 子类在定义时就会解析
# 构造参数，所以 Repository 必须先入库。
app.dependency_container.inject(Repository)


class CatalogService(BaseService):
    """继承 BaseService 后会自动注册进容器，无需手动 inject。"""

    model_class = None

    def __init__(self, repo: Repository):
        self.repo = repo

    def title_of(self, key: str):
        value = self.repo.find(key)
        return None if value is None else f'Item {value}'


# --------------------------------------------------------------------------- #
# 2. 控制器构造注入
# --------------------------------------------------------------------------- #

@controller('/catalog', summary='目录', router=app.router)
class CatalogController:
    def __init__(self, service: CatalogService):
        # service 由容器构造并注入，其依赖 Repository 也会被一并解析
        self.service = service

    @route('/{key}', methods=['GET'], summary='按 ID 查询')
    def get(self, key: str):
        return {'key': key, 'title': self.service.title_of(key)}

    @route('/manual/{key}', methods=['GET'], summary='在函数内手动取用')
    def manual(self, key: str):
        # provider(...) 在任意位置取用同一容器中的实例
        return {'title': provider(CatalogService).title_of(key)}


def main():
    client = TestClient(app)

    print('--- 控制器构造注入 ---')
    print('GET /catalog/1 ->', client.get('/catalog/1').json())
    print('GET /catalog/9 ->', client.get('/catalog/9').json())

    print('\n--- 函数内 provider() ---')
    print('GET /catalog/manual/2 ->', client.get('/catalog/manual/2').json())

    print('\n--- 容器中已注册的依赖 ---')
    for name in sorted(app.dependency_container.dependency_definitions):
        print(' ', name)

    print('\n--- 同一实例被复用（默认 singleton 作用域）---')
    print('provider(CatalogService) is provider(CatalogService) ->',
          provider(CatalogService) is provider(CatalogService))


if __name__ == '__main__':
    main()
