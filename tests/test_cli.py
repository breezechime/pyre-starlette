"""CLI：命令别名、短选项、四种生成来源与脚手架命令。"""
import os
import sys

import pytest

from pyre_starlette import cli


def run_cli(monkeypatch, *argv):
    """以 ``pyre <argv>`` 的方式调用 CLI。"""
    monkeypatch.setattr(sys, "argv", ["pyre", *argv])
    cli.main()


def sqlite_table(path: str, ddl: str) -> None:
    """在 sqlite 文件里建一张表，模拟「项目里已有表」。"""
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text(ddl))
    engine.dispose()


LEGACY_DDL = """
CREATE TABLE system_area (
    id INTEGER NOT NULL PRIMARY KEY,
    parent_id INTEGER,
    name VARCHAR(64) NOT NULL,
    code VARCHAR(32),
    is_enable BOOLEAN DEFAULT 1
)
"""


@pytest.fixture
def legacy_db(workdir):
    """一个带 ``system_area`` 表的 sqlite 库，返回可直接使用的连接串。"""
    target = workdir / "resource"
    target.mkdir(exist_ok=True)
    db_path = target / "legacy.db"
    sqlite_table(str(db_path), LEGACY_DDL)
    return f"sqlite:///{db_path.as_posix()}"


@pytest.fixture
def project_with_datasource(workdir, legacy_db):
    """把数据源写进项目配置，供「先读配置」的用例使用。"""
    resource = workdir / "resource"
    (resource / "application.toml").write_text(
        '[pyre.config]\nenv = "dev"\n', encoding="utf-8"
    )
    (resource / "application-dev.toml").write_text(
        '\n[pyre.datasource]\nurl = "sqlite:///./resource/legacy.db"\necho = false\n',
        encoding="utf-8",
    )
    return workdir


@pytest.fixture
def apps_package(workdir):
    """``apps/__init__.py`` —— 生成物里的 ``from apps import api_router`` 需要它。"""
    apps = workdir / "apps"
    apps.mkdir(exist_ok=True)
    (apps / "__init__.py").write_text(
        "from pyre_starlette import Router\n\n"
        "api_router = Router()\n"
        "admin_router = Router()\n",
        encoding="utf-8",
    )
    return apps


# ---------------------------------------------------------------------------
# 顶层帮助与列举
# ---------------------------------------------------------------------------

def test_no_command_prints_help(monkeypatch, workdir, capsys):
    run_cli(monkeypatch)
    out = capsys.readouterr().out
    assert "usage: pyre" in out
    for command in ("new", "run", "make", "list", "eject", "doctor"):
        assert command in out


def test_help_lists_every_generation_kind(monkeypatch, workdir, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "--help")
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for kind in cli.KIND_NAMES:
        assert kind in out
    # 生成来源在 epilog 里有完整说明
    assert "--fields" in out
    assert "--from-model" in out


def test_list_kinds(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "list")
    out = capsys.readouterr().out
    assert "生成类型:" in out
    assert "controller | c" in out
    assert "sync | sy" in out


def test_list_templates_shows_builtin_names(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "list", "templates")
    out = capsys.readouterr().out.replace("\\", "/")
    assert "默认模板目录" in out
    assert "module/models.py.j2" in out
    assert "project/app.py.j2" in out
    assert "controller/base.j2" not in out


def test_eject_copies_template(monkeypatch, workdir, capsys):
    from pyre_starlette.applications.code_generator import PyreCodeGenerator

    run_cli(monkeypatch, "eject", "module/models.py")
    assert "模板导出成功" in capsys.readouterr().out

    target = workdir / "templates" / "module" / "models.py.j2"
    assert target.exists()
    source = os.path.join(
        PyreCodeGenerator().default_template_dir, "module", "models.py.j2"
    )
    with open(source, encoding="utf-8") as handle:
        assert target.read_text(encoding="utf-8") == handle.read()


def test_eject_missing_template_exits(monkeypatch, workdir, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "eject", "not/exist")
    assert exc.value.code == 1
    assert "模板不存在" in capsys.readouterr().err


def test_legacy_templates_command_still_works(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "templates", "list")
    assert "module/models.py.j2" in capsys.readouterr().out.replace("\\", "/")

    run_cli(monkeypatch, "templates", "eject", "module/schema.py")
    assert (workdir / "templates" / "module" / "schema.py.j2").exists()

    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "templates")
    assert exc.value.code == 1
    assert "未知的模板操作" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# new / run / doctor
# ---------------------------------------------------------------------------

def test_new_scaffolds_project(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "new", "demo", "-p", "8123", "-d", "sqlite:///./resource/app.db")
    out = capsys.readouterr().out
    assert "项目 demo 已创建" in out
    assert "cd demo" in out

    root = workdir / "demo"
    for relative in (
        "app.py",
        "apps/__init__.py",
        "resource/application.toml",
        "resource/application-dev.toml",
        "README.md",
    ):
        assert (root / relative).exists(), relative

    assert "port = 8123" in (root / "resource" / "application.toml").read_text(encoding="utf-8")
    assert "sqlite:///./resource/app.db" in (
        root / "resource" / "application-dev.toml"
    ).read_text(encoding="utf-8")


def test_new_refuses_non_empty_dir_without_force(monkeypatch, workdir, capsys):
    (workdir / "demo").mkdir()
    (workdir / "demo" / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "new", "demo")
    assert exc.value.code == 1
    assert "错误" in capsys.readouterr().err


def test_new_dry_run_writes_nothing(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "new", "demo", "-n")
    assert "[dry-run]" in capsys.readouterr().out
    assert not (workdir / "demo").exists() or not list((workdir / "demo").iterdir())


def test_run_without_entrypoint_exits(monkeypatch, workdir, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "run")
    assert exc.value.code == 1
    assert "未找到" in capsys.readouterr().err


def test_run_boots_app_module(monkeypatch, workdir):
    (workdir / "app.py").write_text("app = object()\n", encoding="utf-8")
    calls = {}

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda target, **kw: calls.update(target=target, **kw))

    run_cli(monkeypatch, "run", "--host", "0.0.0.0", "--port", "9001")

    assert calls["target"] == "app:app"
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 9001
    assert calls["reload"] is True


def test_run_no_reload_flag(monkeypatch, workdir):
    (workdir / "main.py").write_text("app = object()\n", encoding="utf-8")
    calls = {}

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda target, **kw: calls.update(target=target, **kw))

    run_cli(monkeypatch, "run", "--no-reload")
    assert calls["target"] == "main:app"
    assert calls["reload"] is False


def test_doctor_reports_project_state(monkeypatch, project_with_datasource, capsys):
    run_cli(monkeypatch, "doctor")
    out = capsys.readouterr().out
    assert "项目根目录" in out
    assert "未找到 apps/" in out
    assert "数据源" in out
    assert "resource/legacy.db" in out


# ---------------------------------------------------------------------------
# make：四种生成来源
# ---------------------------------------------------------------------------

def test_make_module_empty_shell_writes_six_files(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "make", "module", "article", "-a", "content")
    out = capsys.readouterr().out
    assert "Article 模块（空壳）" in out
    assert "apps/content/article/" in out

    target = workdir / "apps" / "content" / "article"
    for name in ("__init__.py", "enums.py", "models.py", "schema.py", "service.py", "controller.py"):
        assert (target / name).exists(), name

    models = (target / "models.py").read_text(encoding="utf-8")
    assert "class Article(models.Model, models.PkMixin, models.TimestampMixin):" in models
    assert "__tablename__ = 'content_article'" in models
    assert "# TODO: 补充字段" in models


def test_make_top_level_shortcut_matches_make_subcommand(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "make", "c", "article", "-a", "content", "-n")
    via_make = capsys.readouterr().out

    run_cli(monkeypatch, "c", "article", "-a", "content", "-n")
    via_shortcut = capsys.readouterr().out

    assert via_make == via_shortcut
    assert "controller.py" in via_make
    assert not (workdir / "apps" / "content" / "article").exists()


def test_make_short_options_and_multi_letter_aliases(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "mk", "mod", "goods", "-a", "shop", "-c", "GoodsItem", "-n")
    out = capsys.readouterr().out
    assert "GoodsItem 模块" in out
    assert "apps/shop/goods/" in out


def test_make_dry_run_v_echoes_content(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "module", "article", "-a", "content", "-n", "-v")
    out = capsys.readouterr().out
    assert "class Article(" in out
    assert not (workdir / "apps" / "content" / "article").exists()


def test_make_requires_name_when_no_source(monkeypatch, workdir, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "module")
    assert exc.value.code == 1
    assert "缺少名称" in capsys.readouterr().err


def test_make_fields_source(monkeypatch, workdir):
    run_cli(
        monkeypatch, "module", "goods", "-a", "shop",
        "-f", "id:bigint!@#序号,name:str:64!#商品名称,price:decimal:12,2!#价格"
           ",stock:int,is_on:bool=True,tag:json,kind:enum",
        "--comment", "商品",
    )
    target = workdir / "apps" / "shop" / "goods"
    models = (target / "models.py").read_text(encoding="utf-8")
    assert "id = models.AutoPkField(comment='序号')" in models
    assert "name = models.StringField(64, nullable=False, comment='商品名称')" in models
    assert "price = models.DecimalField(precision=12, scale=2, nullable=False, comment='价格')" in models
    assert "is_on = models.BooleanField(default=True)" in models
    assert "tag = models.JSONField()" in models
    assert "kind = models.EnumField(Kind)" in models
    assert "from .enums import Kind" in models

    schema = (target / "schema.py").read_text(encoding="utf-8")
    assert "from decimal import Decimal" in schema
    assert "from typing import Any, Optional" in schema
    assert "price: Optional[Decimal] = Field(None, description='价格')" in schema
    assert "kind: Optional[str] = Field(None)" in schema

    enums = (target / "enums.py").read_text(encoding="utf-8")
    assert "class Kind(enum.Enum):" in enums
    # 空枚举必须带占位成员，否则 EnumField 任何取值都会 LookupError
    assert "UNKNOWN = 'UNKNOWN'" in enums


def test_generated_module_imports_cleanly(monkeypatch, workdir, apps_package):
    """生成结果必须是语法正确、可 import 的运行态代码。"""
    import importlib
    import py_compile

    run_cli(
        monkeypatch, "module", "goods", "-a", "shop",
        "-f", "id:bigint!@#序号,name:str:64!#商品名称,price:decimal:12,2,kind:enum",
    )
    module_dir = workdir / "apps" / "shop" / "goods"
    for name in ("enums.py", "models.py", "schema.py", "service.py", "controller.py"):
        py_compile.compile(str(module_dir / name), doraise=True)

    for key in [name for name in sys.modules if name == "apps" or name.startswith("apps.")]:
        del sys.modules[key]
    monkeypatch.syspath_prepend(str(workdir))

    enums = importlib.import_module("apps.shop.goods.enums")
    models = importlib.import_module("apps.shop.goods.models")
    schema = importlib.import_module("apps.shop.goods.schema")
    service = importlib.import_module("apps.shop.goods.service")
    controller = importlib.import_module("apps.shop.goods.controller")

    assert enums.Kind
    assert models.Goods.__tablename__ == "shop_goods"
    assert {"id", "name", "price", "kind"} <= set(models.Goods.__table__.columns.keys())
    assert "price" in schema.GoodsParams.model_fields
    assert "price" in schema.GoodsResponse.model_fields
    assert service.GoodsService.model_class is models.Goods
    assert "list" in controller.GoodsController.__dict__


def test_make_unknown_field_type_fails(monkeypatch, workdir, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "module", "goods", "-f", "name:unknown")
    assert exc.value.code == 1
    assert "未知字段类型" in capsys.readouterr().err


def test_crud_positional_name_is_table(monkeypatch, project_with_datasource, capsys):
    run_cli(monkeypatch, "crud", "system_area", "-a", "system")
    out = capsys.readouterr().out
    assert "Area 模块（表 system_area）" in out
    assert "apps/system/area/" in out


def test_crud_without_table_fails(monkeypatch, workdir, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "crud", "-a", "system")
    assert exc.value.code == 1
    assert "crud 需要表名" in capsys.readouterr().err


def test_table_reflection_uses_explicit_dsn(monkeypatch, workdir, legacy_db, capsys):
    run_cli(monkeypatch, "module", "system_area", "-a", "system", "-t", "system_area", "-d", legacy_db)
    out = capsys.readouterr().out
    assert "表 system_area" in out

    models = (workdir / "apps" / "system" / "area" / "models.py").read_text(encoding="utf-8")
    assert "class Area(models.Model):" in models
    assert "__tablename__ = 'system_area'" in models
    assert "name = models.StringField(64, nullable=False)" in models
    assert "TimestampMixin" not in models
    assert "parent_id = models.IntegerField()" in models


def test_table_reflection_missing_dsn_fails(monkeypatch, workdir, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "crud", "system_area", "-a", "system")
    assert exc.value.code == 1
    assert "未找到数据源" in capsys.readouterr().err


def test_table_reflection_unknown_table_fails(monkeypatch, workdir, legacy_db, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "crud", "nope", "-t", "nope", "-d", legacy_db)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "不存在" in err
    assert "system_area" in err


def test_force_overwrites_existing_file(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "module", "article", "-a", "content")
    capsys.readouterr()

    target = workdir / "apps" / "content" / "article" / "models.py"
    target.write_text("hand written\n", encoding="utf-8")

    run_cli(monkeypatch, "module", "article", "-a", "content")
    assert "跳过 models.py" in capsys.readouterr().out
    assert target.read_text(encoding="utf-8") == "hand written\n"

    run_cli(monkeypatch, "module", "article", "-a", "content", "-y")
    assert "hand written" not in target.read_text(encoding="utf-8")


def test_register_writes_import_line(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "new", "demo")
    capsys.readouterr()

    run_cli(monkeypatch, "module", "article", "-a", "content", "-R", "-o", "demo")
    out = capsys.readouterr().out
    assert "已写入注册表" in out

    registry = (workdir / "demo" / "apps" / "__init__.py").read_text(encoding="utf-8")
    assert "from .content.article.controller import ArticleController  # noqa" in registry

    run_cli(monkeypatch, "module", "article", "-a", "content", "-R", "-o", "demo")
    assert "注册表已是期望内容" in capsys.readouterr().out


def test_register_skipped_without_controller(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "new", "demo")
    capsys.readouterr()

    run_cli(monkeypatch, "model", "article", "-a", "content", "-f", "name:str", "-R", "-o", "demo")
    out = capsys.readouterr().out
    assert "跳过 -R 注册" in out
    registry = (workdir / "demo" / "apps" / "__init__.py").read_text(encoding="utf-8")
    assert "ArticleController" not in registry


def test_make_app_group(monkeypatch, workdir, capsys):
    run_cli(monkeypatch, "a", "content")
    assert "应用分组 content 已创建" in capsys.readouterr().out
    assert (workdir / "apps" / "content" / "__init__.py").exists()


# ---------------------------------------------------------------------------
# sync：模型 -> schema.py 增量同步
# ---------------------------------------------------------------------------

MODEL_SOURCE = '''"""条目模型。"""

from pyre_starlette import models

from .enums import Kind


class Item(models.Model, models.TimestampMixin):
    """条目"""

    __tablename__ = 'demo_item'
    __table_args__ = {'comment': '条目'}

    id = models.AutoPkField(comment='序号')
    name = models.StringField(64, nullable=False, comment='名称')
    price = models.DecimalField(precision=12, scale=2, comment='价格')
    on_sale_at = models.DateTimeField(comment='上架时间')
    day = models.DateField(comment='日期')
    tag = models.JSONField(comment='标签')
    kind = models.EnumField(Kind, comment='类型')
'''

SCHEMA_SOURCE = '''"""条目请求与返回对象。"""

from typing import Optional
from pydantic import BaseModel, Field


class ItemParams(BaseModel):
    """条目保存参数"""

    id: Optional[int] = Field(None, description='序号')
    name: Optional[str] = Field(None, description='名称')


class ItemResponse(BaseModel):
    """条目返回对象"""

    id: Optional[int] = Field(None, description='序号')
'''


@pytest.fixture
def syncable_module(workdir):
    target = workdir / "apps" / "demo" / "item"
    target.mkdir(parents=True)
    (target / "__init__.py").write_text('"""条目模块。"""\n', encoding="utf-8")
    (target / "models.py").write_text(MODEL_SOURCE, encoding="utf-8")
    (target / "schema.py").write_text(SCHEMA_SOURCE, encoding="utf-8")
    return target


def test_sync_requires_from_model(monkeypatch, workdir, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "sync")
    assert exc.value.code == 1
    assert "sync 需要 -m/--from-model" in capsys.readouterr().err


def test_sync_appends_missing_fields_and_imports(monkeypatch, syncable_module, capsys):
    run_cli(monkeypatch, "sync", "-m", "apps/demo/item/models.py")
    out = capsys.readouterr().out
    assert "同步 schema" in out
    assert "ItemParams 新增 5 个字段" in out
    assert "ItemResponse 新增 6 个字段" in out

    text = (syncable_module / "schema.py").read_text(encoding="utf-8")
    # 原有字段保留
    assert "name: Optional[str] = Field(None, description='名称')" in text
    # 新字段追加在类体末尾
    assert "kind: Optional[str] = Field(None, description='类型')" in text
    assert "price: Optional[Decimal] = Field(None, description='价格')" in text
    assert "day: Optional[date] = Field(None, description='日期')" in text
    # import 补齐且并入已有的 typing 行
    assert "from typing import Any, Optional" in text
    assert "from decimal import Decimal" in text
    assert "from datetime import date, datetime" in text
    # 枚举不引入 ORM 类型
    assert "Optional[Kind]" not in text


def test_sync_is_idempotent(monkeypatch, syncable_module, capsys):
    run_cli(monkeypatch, "sync", "-m", "apps/demo/item/models.py")
    first = (syncable_module / "schema.py").read_text(encoding="utf-8")
    capsys.readouterr()

    run_cli(monkeypatch, "sync", "-m", "apps/demo/item/models.py")
    assert "无需改动，schema 已与模型一致" in capsys.readouterr().out
    assert (syncable_module / "schema.py").read_text(encoding="utf-8") == first


def test_sync_dry_run_does_not_write(monkeypatch, syncable_module, capsys):
    run_cli(monkeypatch, "sync", "-m", "apps/demo/item/models.py", "-n")
    assert "[dry-run]" in capsys.readouterr().out
    assert (syncable_module / "schema.py").read_text(encoding="utf-8") == SCHEMA_SOURCE


def test_sync_reports_stale_schema_fields_without_deleting(monkeypatch, workdir, capsys):
    target = workdir / "apps" / "demo" / "item"
    target.mkdir(parents=True)
    (target / "models.py").write_text(MODEL_SOURCE, encoding="utf-8")
    (target / "schema.py").write_text(
        SCHEMA_SOURCE.replace(
            "    name: Optional[str] = Field(None, description='名称')",
            "    name: Optional[str] = Field(None, description='名称')\n"
            "    legacy: Optional[str] = Field(None, description='已废弃')",
        ),
        encoding="utf-8",
    )

    run_cli(monkeypatch, "sync", "-m", "apps/demo/item/models.py")
    out = capsys.readouterr().out
    assert "仅提示，未删除" in out
    assert "legacy" in out
    assert "legacy" in (target / "schema.py").read_text(encoding="utf-8")


def test_sync_skips_missing_classes(monkeypatch, workdir, capsys):
    target = workdir / "apps" / "demo" / "item"
    target.mkdir(parents=True)
    (target / "models.py").write_text(MODEL_SOURCE, encoding="utf-8")
    (target / "schema.py").write_text('"""空。"""\n', encoding="utf-8")

    run_cli(monkeypatch, "sync", "-m", "apps/demo/item/models.py")
    out = capsys.readouterr().out
    assert "ItemParams 不存在，未同步" in out
    assert "ItemResponse 不存在，未同步" in out


# ---------------------------------------------------------------------------
# model：按已有模型生成
# ---------------------------------------------------------------------------

def test_make_from_existing_model_infers_name(monkeypatch, syncable_module, workdir, capsys):
    run_cli(monkeypatch, "module", "-m", "apps/demo/item/models.py", "-n")
    out = capsys.readouterr().out
    assert "Item 模块（已有模型）" in out
    assert "apps/demo/item/" in out


def test_make_from_existing_model_class_selector(monkeypatch, syncable_module, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "module", "-m", "apps/demo/item/models.py:Missing", "-n")
    assert exc.value.code == 1
    assert "没有模型类" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 单文件生成：自动补齐硬依赖
# ---------------------------------------------------------------------------

def test_single_file_kind_backfills_dependencies(monkeypatch, workdir, capsys):
    """只生成 models.py 时，必须同时补上 __init__.py 与 enums.py，否则导入即失败。"""
    run_cli(monkeypatch, "m", "goods", "-a", "shop", "-f", "id:bigint!@#,kind:enum")
    out = capsys.readouterr().out
    assert "自动补齐硬依赖" in out

    target = workdir / "apps" / "shop" / "goods"
    for name in ("__init__.py", "models.py", "enums.py"):
        assert (target / name).is_file(), name
    assert "from .enums import Kind" in (target / "models.py").read_text(encoding="utf-8")
    assert "class Kind(enum.Enum):" in (target / "enums.py").read_text(encoding="utf-8")


def test_single_file_kind_backfills_init_without_enum(monkeypatch, workdir, capsys):
    """没有枚举字段时只补 __init__.py，不该凭空造 enums.py。"""
    run_cli(monkeypatch, "sc", "post", "-a", "content")
    out = capsys.readouterr().out
    assert "自动补齐硬依赖：__init__.py" in out

    target = workdir / "apps" / "content" / "post"
    assert (target / "__init__.py").is_file()
    assert (target / "schema.py").is_file()
    assert not (target / "enums.py").exists()


def test_single_file_kind_does_not_backfill_existing(monkeypatch, workdir, capsys):
    """依赖已存在时不重复生成（也不应打印补齐说明）。"""
    target = workdir / "apps" / "shop" / "goods"
    target.mkdir(parents=True)
    (target / "__init__.py").write_text("", encoding="utf-8")
    (target / "enums.py").write_text("import enum\n", encoding="utf-8")

    run_cli(monkeypatch, "m", "goods", "-a", "shop", "-f", "id:bigint!@#,kind:enum")
    out = capsys.readouterr().out
    assert "自动补齐硬依赖" not in out
    assert "import enum\n" == (target / "enums.py").read_text(encoding="utf-8")
