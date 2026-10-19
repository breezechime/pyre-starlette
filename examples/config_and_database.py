"""配置加载 + 数据库：读取 ``examples/resource`` 下的 toml，并完成一次 SQLite CRUD。

在仓库根目录执行：``python examples/config_and_database.py``

配置优先级（低 → 高）：
调用方默认值 → application.toml → application-dev.toml → 环境变量（SERVER_* / PYRE_*）
"""
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

for _key in [key for key in os.environ if key.startswith(('SERVER_', 'PYRE_'))]:
    os.environ.pop(_key, None)

# 配置扫描器默认查找 ./config、./resource，因此切到示例目录
os.chdir(HERE)

from starlette.testclient import TestClient  # noqa: E402

from pyre_starlette import (  # noqa: E402
    BaseService,
    PyreStarlette,
    controller,
    models,
    route,
)

app = PyreStarlette(notice=False)
logging.getLogger().setLevel(logging.ERROR)


# --------------------------------------------------------------------------- #
# 1. 模型：继承 models.Model，按需混入主键 / 时间戳
# --------------------------------------------------------------------------- #

class Note(models.Model, models.PkMixin, models.TimestampMixin):
    __tablename__ = 'note'
    __table_args__ = {'comment': '示例便签'}

    title = models.StringField(128, nullable=False, comment='标题')


app.db.create_all()


# --------------------------------------------------------------------------- #
# 2. 服务：BaseService 自带分页 / 排序 / 条件构建等工具方法
# --------------------------------------------------------------------------- #

class NoteService(BaseService):
    model_class = Note


# --------------------------------------------------------------------------- #
# 3. 控制器
# --------------------------------------------------------------------------- #

@controller('/notes', summary='便签', router=app.router)
class NoteController:
    def __init__(self, service: NoteService):
        self.service = service

    @route('/add', methods=['POST'], summary='新增')
    def add(self, title: str):
        note = Note(title=title)
        note.save()
        return {'id': note.id, 'title': note.title}

    @route('/all', methods=['GET'], summary='全部')
    def all_notes(self):
        return {'count': Note.query.count(), 'titles': [n.title for n in Note.query.all()]}


def main():
    print('--- 扫描到的配置文件 ---')
    for name, path in app.config_loader.scanner.scanner().items():
        print(f'  {name:26} -> {os.path.relpath(path, HERE)}')

    print('\n--- 生效的配置 ---')
    print('pyre.config.env        =', app.app_config.pyre.config.env)
    print('pyre.config.envs       =', app.app_config.pyre.config.envs)
    print('server.port            =', app.app_config.server.port)
    print('pyre.datasource.url    =', app.app_config.pyre.datasource.url)
    print('environment.is_dev()   =', app.environment.is_dev())

    print('\n--- 数据库中间件 ---')
    print('已装载中间件：', [mw.cls.__name__ for mw in app.user_middleware])

    client = TestClient(app)
    print('\n--- CRUD ---')
    print('POST /notes/add?title=first ->', client.post('/notes/add?title=first').json())
    print('POST /notes/add?title=second->', client.post('/notes/add?title=second').json())
    print('GET  /notes/all             ->', client.get('/notes/all').json())

    print('\n--- 环境变量覆盖（SERVER_PORT 优先于配置文件）---')
    os.environ['SERVER_PORT'] = '9999'
    reloaded = PyreStarlette(notice=False)
    logging.getLogger().setLevel(logging.ERROR)
    print('server.port =', reloaded.app_config.server.port)


if __name__ == '__main__':
    main()
