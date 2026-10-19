"""代码生成器内部：命名转换、字段语法、四种来源与模板渲染。"""
import os

import pytest

from pyre_starlette.applications.code_generator import (
    PyreCodeGenerator,
    to_camel_case,
    to_kebab_case,
    to_pascal_case,
    to_snake_case,
)
from pyre_starlette.applications.code_generator import sources
from pyre_starlette.applications.code_generator.generators import (
    MODULE_FILES,
    ModuleGenerator,
    register_controller,
)
from pyre_starlette.applications.code_generator.spec import (
    FieldSpec,
    ModuleSpec,
    parse_fields,
    resolve_type,
    safe_identifier,
)

MODEL_SOURCE = '''"""订单模型。"""

import sqlalchemy_db.models as m

from .enums import Status


class Order(m.Model, m.TimestampMixin, m.SoftDeleteMixin):
    """订单"""

    __tablename__ = 'shop_order'

    id = m.AutoPkField(comment='序号')
    order_no = m.StringField(32, nullable=False, unique=True, comment='单号')
    amount = m.DecimalField(precision=12, scale=2, comment='金额')
    status = m.EnumField(Status, comment='状态')
    remark = m.TextField()
    paid_at = m.DateTimeField(comment='支付时间')
'''


# ---------------------------------------------------------------------------
# 命名与工具
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("system_area", "SystemArea"),
        ("systemArea", "SystemArea"),
        ("system-area", "SystemArea"),
        ("SystemArea", "SystemArea"),
        ("shop.order.item", "ShopOrderItem"),
    ],
)
def test_to_pascal_case(raw, expected):
    assert to_pascal_case(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("SystemArea", "system_area"),
        ("system-area", "system_area"),
        ("systemArea", "system_area"),
        ("HTTPServer", "http_server"),
    ],
)
def test_to_snake_case(raw, expected):
    assert to_snake_case(raw) == expected


def test_to_camel_and_kebab_case():
    assert to_camel_case("system_area") == "systemArea"
    assert to_kebab_case("SystemArea") == "system-area"
    assert to_pascal_case("") == ""
    assert to_snake_case("") == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Order No", "order_no"),
        ("1st", "_1st"),
        ("class", "class_"),
        ("", "field"),
    ],
)
def test_safe_identifier(raw, expected):
    assert safe_identifier(raw) == expected


def test_resolve_type_aliases():
    assert resolve_type("varchar") == "str"
    assert resolve_type("TIMESTAMP") == "datetime"
    assert resolve_type("e") == "enum"
    with pytest.raises(ValueError):
        resolve_type("nope")


# ---------------------------------------------------------------------------
# --fields 内联字段
# ---------------------------------------------------------------------------

def test_parse_fields_basic():
    fields = parse_fields("name:str:64!#名称,age:int,is_on:bool=True")
    assert [item.name for item in fields] == ["name", "age", "is_on"]
    name, age, is_on = fields
    assert (name.type, name.length, name.nullable, name.comment) == ("str", 64, False, "名称")
    assert age.type == "int"
    assert is_on.default == "True"


def test_parse_fields_keeps_decimal_precision_scale():
    fields = parse_fields("price:decimal:12,2!#价格,stock:int")
    assert [item.name for item in fields] == ["price", "stock"]
    assert (fields[0].precision, fields[0].scale) == (12, 2)


def test_parse_fields_separators_and_primary_key():
    fields = parse_fields("id:bigint!@#序号;title:str:32")
    assert [item.name for item in fields] == ["id", "title"]
    assert fields[0].primary_key and not fields[0].nullable
    assert fields[0].autoincrement is True


def test_enum_field_rendering():
    spec = ModuleSpec(name="goods", fields=parse_fields("kind:enum,level:intenum"))
    assert "kind = models.EnumField(Kind)" in spec.model_fields
    assert "level = models.IntEnumField(Level)" in spec.model_fields
    assert spec.enum_import_line == "from .enums import Kind, Level"


def test_enum_base_and_placeholder():
    """空枚举要带占位成员，且基类与占位取值随枚举类型变化，否则生成代码不可运行。"""
    base = ModuleSpec(name="goods", fields=parse_fields("kind:enum"))
    assert base.needed_enums[0].enum_base == "Enum"
    assert base.needed_enums[0].enum_placeholder == "UNKNOWN = 'UNKNOWN'"

    int_spec = ModuleSpec(name="goods", fields=parse_fields("level:intenum"))
    assert int_spec.needed_enums[0].enum_base == "IntEnum"
    assert int_spec.needed_enums[0].enum_placeholder == "UNKNOWN = 0"

    str_spec = ModuleSpec(name="goods", fields=parse_fields("status:strenum"))
    assert str_spec.needed_enums[0].enum_base == "StrEnum"
    assert str_spec.needed_enums[0].enum_placeholder == "UNKNOWN = 'unknown'"


def test_enum_schema_type_follows_storage():
    """schema 层枚举降级后的类型要与底层存取方式一致（名 -> str，整型值 -> int）。"""
    fields = {item.name: item for item in parse_fields("kind:enum,level:intenum,status:strenum")}
    assert fields["kind"].schema_python_type == "str"
    assert fields["level"].schema_python_type == "int"
    assert fields["status"].schema_python_type == "str"


def test_enums_template_renders_placeholder():
    from pyre_starlette.applications.code_generator import PyreCodeGenerator

    spec = ModuleSpec(name="goods", class_name="Goods", fields=parse_fields("kind:enum,level:intenum"))
    text = PyreCodeGenerator().render_template("module/enums.py.j2", **spec.to_context())
    assert "class Kind(enum.Enum):" in text
    assert "class Level(enum.IntEnum):" in text
    assert "UNKNOWN = 'UNKNOWN'" in text
    assert "UNKNOWN = 0" in text


def test_field_expression_uses_autopk_for_auto_pk():
    field = FieldSpec(name="id", type="bigint", primary_key=True, autoincrement=True, comment="序号")
    assert field.model_line() == "id = models.AutoPkField(comment='序号')"


def test_field_expression_keeps_plain_pk_when_not_auto():
    field = FieldSpec(name="code", type="str", length=32, primary_key=True, autoincrement=False)
    assert field.model_line() == (
        "code = models.StringField(32, primary_key=True, autoincrement=False)"
    )


# ---------------------------------------------------------------------------
# 空壳来源
# ---------------------------------------------------------------------------

def test_empty_spec_defaults():
    spec = sources.empty_spec("article", app="content", comment="文章")
    assert spec.module_dir == "apps/content/article"
    assert spec.package == "apps.content.article"
    assert spec.table_name == "content_article"
    assert spec.path == "/content/article"
    assert spec.class_name == "Article"
    assert spec.controller_class == "ArticleController"
    assert spec.service_class == "ArticleService"
    assert spec.fields == []
    assert spec.source == "empty"


def test_empty_spec_without_app():
    spec = sources.empty_spec("article")
    assert spec.table_name == "article"
    assert spec.path == "/article"
    assert spec.module_dir == "apps/article"


def test_module_spec_drops_mixins_already_declared_as_columns():
    spec = ModuleSpec(
        name="order",
        fields=parse_fields("id:bigint!@#,create_time:datetime,delete_time:datetime"),
    )
    assert spec.with_pk_mixin is False
    assert spec.with_timestamp is False
    assert spec.with_soft_delete is False
    assert spec.bases == "models.Model"


def test_module_spec_rejects_empty_name():
    with pytest.raises(ValueError):
        ModuleSpec(name="  ")


# ---------------------------------------------------------------------------
# 模型来源（AST 静态解析）
# ---------------------------------------------------------------------------

@pytest.fixture
def model_file(workdir):
    target = workdir / "apps" / "shop" / "order"
    target.mkdir(parents=True)
    (target / "models.py").write_text(MODEL_SOURCE, encoding="utf-8")
    return target / "models.py"


def test_parse_model_file_handles_import_alias(model_file):
    parsed = sources.parse_model_file(str(model_file))
    assert "Order" in parsed
    order = parsed["Order"]
    assert order["table_name"] == "shop_order"
    assert order["comment"] == "订单"
    assert order["with_timestamp"] and order["with_soft_delete"]

    fields = {item["name"]: item for item in order["fields"]}
    assert fields["id"]["primary_key"] is True
    assert fields["id"]["autoincrement"] is True
    assert fields["order_no"]["length"] == 32
    assert fields["order_no"]["unique"] is True
    assert (fields["amount"]["precision"], fields["amount"]["scale"]) == (12, 2)
    assert fields["status"]["enum_class"] == "Status"
    assert fields["remark"]["type"] == "text"


def test_model_spec_round_trip(model_file, monkeypatch):
    monkeypatch.chdir(model_file.parents[3])
    spec = sources.model_spec("apps/shop/order/models.py")
    assert spec.name == "order"
    assert spec.app == "shop"
    assert spec.class_name == "Order"
    assert spec.table_name == "shop_order"
    assert spec.source == "model"
    assert spec.with_pk_mixin is False
    assert spec.with_timestamp and spec.with_soft_delete

    by_name = {item.name: item for item in spec.fields}
    assert by_name["id"].model_line() == "id = models.AutoPkField(comment='序号')"
    assert by_name["status"].model_line() == "status = models.EnumField(Status, comment='状态')"


def test_model_spec_accepts_dotted_and_class_selector(model_file, monkeypatch):
    root = model_file.parents[3]
    monkeypatch.chdir(root)
    assert sources.model_spec("apps.shop.order.models").class_name == "Order"
    assert sources.model_spec("apps/shop/order/models.py:Order").class_name == "Order"
    with pytest.raises(sources.SourceError):
        sources.model_spec("apps/shop/order/models.py:Nope")


def test_model_spec_missing_file_raises(workdir):
    with pytest.raises(sources.SourceError):
        sources.model_spec("apps/nope/models.py")


def test_module_name_from_path_prefers_package_dir(model_file, monkeypatch):
    monkeypatch.chdir(model_file.parents[3])
    path, cls = sources.resolve_model_target("apps/shop/order/models.py", os.getcwd())
    assert path.replace(os.sep, "/").endswith("apps/shop/order/models.py")
    assert cls is None


# ---------------------------------------------------------------------------
# 表来源（反射）
# ---------------------------------------------------------------------------

def test_table_spec_reflects_sqlite(workdir):
    from sqlalchemy import create_engine, text

    db_path = workdir / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(text(
            """
            CREATE TABLE system_area (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(64) NOT NULL,
                is_enable BOOLEAN DEFAULT 1,
                parent_id INTEGER
            )
            """
        ))
    engine.dispose()

    spec = sources.table_spec("system_area", dsn=f"sqlite:///{db_path}", app="system")
    assert spec.name == "area"
    assert spec.class_name == "Area"
    assert spec.table_name == "system_area"
    assert spec.source == "table"
    assert spec.with_timestamp is False
    assert spec.with_soft_delete is False
    assert spec.with_pk_mixin is False

    by_name = {item.name: item for item in spec.fields}
    assert by_name["name"].length == 64
    assert by_name["name"].nullable is False
    assert by_name["is_enable"].type == "bool"


def test_table_spec_unknown_table_raises(workdir):
    from sqlalchemy import create_engine

    db_path = workdir / "empty.db"
    create_engine(f"sqlite:///{db_path}").dispose()
    with pytest.raises(sources.SourceError) as exc:
        sources.table_spec("nope", dsn=f"sqlite:///{db_path}")
    assert "不存在" in str(exc.value)


def test_table_spec_without_dsn_raises(workdir):
    with pytest.raises(sources.SourceError):
        sources.table_spec("nope")


def test_discover_dsn_prefers_dev_config(workdir):
    resource = workdir / "resource"
    resource.mkdir()
    (resource / "application.toml").write_text(
        '[pyre.datasource]\nurl = "sqlite:///./resource/base.db"\n', encoding="utf-8"
    )
    (resource / "application-dev.toml").write_text(
        '# 注释\n[pyre.datasource]\nurl = "sqlite:///./resource/dev.db"  # 主库\n',
        encoding="utf-8",
    )
    assert sources.discover_dsn(str(workdir)) == "sqlite:///./resource/dev.db"


def test_discover_dsn_returns_none_without_config(workdir):
    assert sources.discover_dsn(str(workdir)) is None


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

@pytest.fixture
def generator(workdir):
    return PyreCodeGenerator(str(workdir))


def test_templates_use_trimmed_indentation(generator):
    spec = sources.fields_spec(
        "goods", "id:bigint!@#序号,name:str:64!#名称,kind:enum",
        app="shop", comment="商品", router="apps:api_router",
    )
    models = generator.render_template("module/models.py.j2", **spec.to_context())
    assert models.startswith('"""商品模型定义。"""\n\nfrom pyre_starlette import models\n')
    assert "\n\n\nclass Goods(" in models
    assert models.endswith("\n")
    assert "    " not in models.split("\n\n")[0]

    controller = generator.render_template("module/controller.py.j2", **spec.to_context())
    assert "from apps import api_router" in controller
    assert "from  import" not in controller
    assert "router=api_router" in controller

    schema = generator.render_template("module/schema.py.j2", **spec.to_context())
    assert "\n\n\nclass GoodsBase(" in schema


def test_controller_omits_router_when_disabled(generator):
    spec = sources.empty_spec("article", app="content", router=None)
    controller = generator.render_template("module/controller.py.j2", **spec.to_context())
    assert "import api_router" not in controller
    assert "router=" not in controller


def test_list_and_eject_templates(generator, workdir):
    names = generator.list_templates()
    for expected in ("module/models.py.j2", "project/app.py.j2", "project/apps/__init__.py.j2"):
        assert expected in names

    target = generator.eject_template("module/schema.py")
    assert os.path.isfile(target)
    assert generator.get_custom_template_dir() is not None

    with pytest.raises(FileNotFoundError):
        generator.eject_template("module/nope.py")


# ---------------------------------------------------------------------------
# ModuleGenerator
# ---------------------------------------------------------------------------

def test_module_generator_writes_files_idempotently(workdir):
    spec = sources.empty_spec("article", app="content", comment="文章")
    first = ModuleGenerator(spec, project_root=str(workdir)).generate()
    assert len(first.written) == len(MODULE_FILES)
    assert first.app_init and os.path.isfile(first.app_init)

    second = ModuleGenerator(spec, project_root=str(workdir)).generate()
    assert second.written == []
    assert len(second.skipped) == len(MODULE_FILES)


def test_module_generator_keeps_hand_written_file(workdir):
    spec = sources.empty_spec("article", app="content", comment="文章")
    ModuleGenerator(spec, project_root=str(workdir)).generate()

    target = os.path.join(str(workdir), "apps", "content", "article", "models.py")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("hand = 1\n")

    result = ModuleGenerator(spec, project_root=str(workdir)).generate()
    assert target in result.skipped

    forced = ModuleGenerator(spec, project_root=str(workdir), force=True).generate()
    assert target in forced.written
    with open(target, encoding="utf-8") as handle:
        assert "hand = 1" not in handle.read()


def test_module_generator_dry_run_keeps_disk_untouched(workdir):
    spec = sources.empty_spec("article", app="content", comment="文章")
    result = ModuleGenerator(spec, project_root=str(workdir), dry_run=True).generate()
    assert len(result.written) == len(MODULE_FILES)
    assert set(result.rendered) == set(result.written)
    assert not os.path.exists(os.path.join(str(workdir), "apps"))


def test_register_controller(workdir):
    init_file = workdir / "apps" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text("api_router = None\n", encoding="utf-8")

    line = register_controller(
        str(workdir), "apps/content/article", "ArticleController"
    )
    assert line == "from .content.article.controller import ArticleController  # noqa"
    assert line in init_file.read_text(encoding="utf-8")

    # 重复注册不做改动
    assert register_controller(str(workdir), "apps/content/article", "ArticleController") is None


def test_register_controller_ignores_commented_hint(workdir):
    init_file = workdir / "apps" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text(
        "# from .content.article.controller import ArticleController  # noqa\n",
        encoding="utf-8",
    )
    assert register_controller(
        str(workdir), "apps/content/article", "ArticleController"
    ) is not None


def test_register_controller_without_registry_returns_none(workdir):
    assert register_controller(str(workdir), "apps/content/article", "XController") is None


# ---------------------------------------------------------------------------
# 兼容层
# ---------------------------------------------------------------------------

def test_legacy_generator_classes_still_work(workdir):
    from pyre_starlette.applications.code_generator import code_generator as legacy

    files = legacy.PyreModuleCodeGenerator('content', str(workdir)).generate(
        'article', comment='文章'
    )
    assert len(files) == len(MODULE_FILES)
    assert os.path.isfile(os.path.join(str(workdir), 'apps', 'content', 'article', 'models.py'))

    controller = legacy.PyreControllerCodeGenerator('content', str(workdir)).generate('article')
    assert os.path.basename(controller) == 'controller.py'
    with open(controller, encoding='utf-8') as handle:
        assert 'from apps import api_router' in handle.read()

    # vo 等价于 schema
    assert issubclass(legacy.PyreVoCodeGenerator, legacy.PyreSchemaCodeGenerator)
    vo_file = legacy.PyreVoCodeGenerator('content', str(workdir)).generate('article')
    assert os.path.basename(vo_file) == 'schema.py'


def test_legacy_table_generator_reflects(workdir):
    from sqlalchemy import create_engine, text

    from pyre_starlette.applications.code_generator import code_generator as legacy

    db_path = workdir / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE system_area (id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(32))")
        )
    engine.dispose()

    import pyre_starlette.applications.code_generator.sources as sources

    original = sources.discover_dsn
    sources.discover_dsn = lambda _root=None: f"sqlite:///{db_path}"
    try:
        files = legacy.PyreTableCodeGenerator('system', str(workdir)).generate('system_area')
    finally:
        sources.discover_dsn = original

    assert len(files) == len(MODULE_FILES)
    with open(os.path.join(str(workdir), 'apps', 'system', 'area', 'models.py'), encoding="utf-8") as handle:
        assert "class SystemArea(models.Model):" in handle.read()


# ---------------------------------------------------------------------------
# sync_schema
# ---------------------------------------------------------------------------

def test_sync_schema_returns_report_and_is_idempotent(workdir):
    from pyre_starlette.applications.code_generator.sync import sync_schema

    target = workdir / "apps" / "shop" / "order"
    target.mkdir(parents=True)
    (target / "models.py").write_text(MODEL_SOURCE, encoding="utf-8")
    (target / "schema.py").write_text(
        '"""订单。"""\n\n'
        "from typing import Optional\n"
        "from pydantic import BaseModel, Field\n\n\n"
        "class OrderParams(BaseModel):\n"
        "    id: Optional[int] = Field(None)\n\n\n"
        "class OrderResponse(BaseModel):\n"
        "    id: Optional[int] = Field(None)\n",
        encoding="utf-8",
    )

    spec = sources.model_spec("apps/shop/order/models.py", project_root=str(workdir))
    assert spec.class_name == "Order"

    report = sync_schema(spec, str(target / "schema.py"))
    assert report.changed
    assert report.missing_classes == []
    # id 属基础字段不同步，其余 5 个字段补进两个类
    assert report.added_count == 10
    assert report.stale == []

    text = (target / "schema.py").read_text(encoding="utf-8")
    assert "order_no: Optional[str] = Field(None, description='单号', max_length=32)" in text
    assert "status: Optional[str] = Field(None, description='状态')" in text
    assert "from decimal import Decimal" in text
    assert "from typing import Optional" in text

    again = sync_schema(spec, str(target / "schema.py"))
    assert not again.changed
    assert (target / "schema.py").read_text(encoding="utf-8") == text


def test_sync_schema_missing_file_raises(workdir):
    from pyre_starlette.applications.code_generator.sync import sync_schema

    spec = sources.empty_spec("article", app="content")
    with pytest.raises(FileNotFoundError):
        sync_schema(spec, str(workdir / "nope" / "schema.py"))


def test_sync_schema_dry_run_keeps_file(workdir):
    from pyre_starlette.applications.code_generator.sync import sync_schema

    target = workdir / "apps" / "shop" / "order"
    target.mkdir(parents=True)
    (target / "models.py").write_text(MODEL_SOURCE, encoding="utf-8")
    original = (
        '"""订单。"""\n\n'
        "from typing import Optional\n"
        "from pydantic import BaseModel, Field\n\n\n"
        "class OrderParams(BaseModel):\n"
        "    id: Optional[int] = Field(None)\n\n\n"
        "class OrderResponse(BaseModel):\n"
        "    id: Optional[int] = Field(None)\n"
    )
    (target / "schema.py").write_text(original, encoding="utf-8")

    spec = sources.model_spec("apps/shop/order/models.py", project_root=str(workdir))
    report = sync_schema(spec, str(target / "schema.py"), dry_run=True)
    assert report.changed
    assert (target / "schema.py").read_text(encoding="utf-8") == original


def test_sync_schema_reports_stale_fields_without_deleting(workdir):
    from pyre_starlette.applications.code_generator.sync import sync_schema

    target = workdir / "apps" / "shop" / "order"
    target.mkdir(parents=True)
    (target / "models.py").write_text(MODEL_SOURCE, encoding="utf-8")
    (target / "schema.py").write_text(
        '"""订单。"""\n\n'
        "from typing import Optional\n"
        "from pydantic import BaseModel, Field\n\n\n"
        "class OrderParams(BaseModel):\n"
        "    id: Optional[int] = Field(None)\n"
        "    order_no: Optional[str] = Field(None)\n"
        "    amount: Optional[str] = Field(None)\n"
        "    status: Optional[str] = Field(None)\n"
        "    remark: Optional[str] = Field(None)\n"
        "    paid_at: Optional[str] = Field(None)\n"
        "    legacy: Optional[str] = Field(None)\n\n\n"
        "class OrderResponse(BaseModel):\n"
        "    id: Optional[int] = Field(None)\n",
        encoding="utf-8",
    )

    spec = sources.model_spec("apps/shop/order/models.py", project_root=str(workdir))
    report = sync_schema(spec, str(target / "schema.py"))
    assert report.stale == ["legacy"]
    assert "legacy" in (target / "schema.py").read_text(encoding="utf-8")
    assert any("未删除" in line for line in report.summary_lines())
