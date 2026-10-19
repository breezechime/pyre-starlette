"""生成来源：空壳 / 内联字段 / 已有表 / 已有模型定义。

四种来源最终都产出 :class:`~.spec.ModuleSpec`，交给同一套模板渲染。
"""
from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import to_pascal_case, to_snake_case
from .spec import (
    ENUM_TYPES,
    FIELD_TYPES,
    SQLALCHEMY_TYPE_MAP,
    FieldSpec,
    ModuleSpec,
    parse_fields,
    py_str,
    resolve_type,
    safe_identifier,
)

#: sqlalchemy_db 字段构造函数名 -> 逻辑类型
BUILDER_TO_TYPE: Dict[str, str] = {
    meta['builder']: name for name, meta in FIELD_TYPES.items()
}
BUILDER_TO_TYPE.update({
    'EnumField': 'enum',
    'IntEnumField': 'intenum',
    'StrEnumField': 'strenum',
    'AutoPkField': 'bigint',
})

#: 构造函数的「尺寸」位置参数含义
LENGTH_BUILDERS = {'StringField', 'StrEnumField'}

#: 默认配置文件名，按优先级从高到低
CONFIG_CANDIDATES = (
    'resource/application-dev.toml',
    'resource/application.toml',
    'application-dev.toml',
    'application.toml',
)


class SourceError(RuntimeError):
    """生成来源解析失败。"""


# ---------------------------------------------------------------------------
# 1. 空壳
# ---------------------------------------------------------------------------

def empty_spec(
    name: str,
    *,
    app: Optional[str] = None,
    class_name: Optional[str] = None,
    table_name: Optional[str] = None,
    comment: str = '',
    path: Optional[str] = None,
    router: Optional[str] = None,
    with_soft_delete: bool = False,
) -> ModuleSpec:
    """生成空壳模块：结构齐全、字段留空。"""
    spec = ModuleSpec(
        name=name,
        app=app,
        class_name=class_name,
        table_name=table_name,
        comment=comment,
        path=path,
        router=router,
        fields=[],
        source='empty',
        with_soft_delete=with_soft_delete,
    )
    if not table_name:
        spec.table_name = f'{spec.app}_{spec.name}' if spec.app else spec.name
    return spec


# ---------------------------------------------------------------------------
# 2. 内联字段
# ---------------------------------------------------------------------------

def fields_spec(name: str, fields_text: str, **kwargs: Any) -> ModuleSpec:
    """按 ``--fields`` 的内联声明生成。"""
    spec = empty_spec(name, **kwargs)
    spec.fields = parse_fields(fields_text)
    spec.source = 'fields'
    spec._sync_pk_mixin()
    return spec


# ---------------------------------------------------------------------------
# 3. 已有表（反射）
# ---------------------------------------------------------------------------

def discover_dsn(project_root: Optional[str] = None) -> Optional[str]:
    """从项目的 ``resource/application*.toml`` 里找出数据源连接串。"""
    root = project_root or os.getcwd()
    for relative in CONFIG_CANDIDATES:
        candidate = os.path.join(root, relative)
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, encoding='utf-8') as handle:
                dsn = _read_datasource_url(handle.read())
        except OSError:
            continue
        if dsn:
            return dsn
    return None


def _read_datasource_url(text: str) -> Optional[str]:
    """极简 TOML 扫描：取 ``[pyre.datasource]``（或 ``[datasource]``）下的 url。"""
    section = None
    url: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line.strip('[]').strip()
            continue
        if section not in ('pyre.datasource', 'datasource'):
            continue
        head, sep, tail = line.partition('=')
        if sep and head.strip() == 'url':
            url = tail.strip().strip('\'"')
    return url


def table_spec(
    table_name: str,
    *,
    dsn: Optional[str] = None,
    project_root: Optional[str] = None,
    app: Optional[str] = None,
    class_name: Optional[str] = None,
    comment: str = '',
    path: Optional[str] = None,
    router: Optional[str] = None,
    with_timestamp: bool = False,
    with_soft_delete: bool = False,
) -> ModuleSpec:
    """反射数据库已有表，生成模块描述。

    默认是**纯反射**：表里有什么列就生成什么字段，不额外叠加
    ``TimestampMixin`` / ``SoftDeleteMixin``，避免模型与既有表结构不一致。
    """
    dsn = dsn or discover_dsn(project_root)
    if not dsn:
        raise SourceError(
            '未找到数据源：请在 resource/application*.toml 配置 [pyre.datasource] url，'
            '或用 -d/--dsn 指定连接串'
        )

    try:
        from sqlalchemy import create_engine, inspect
        from sqlalchemy.exc import ArgumentError
    except ImportError as exc:  # pragma: no cover - sqlalchemy 是硬依赖
        raise SourceError(f'需要 SQLAlchemy 才能反射表结构：{exc}') from exc

    try:
        engine = create_engine(dsn)
    except (ArgumentError, ModuleNotFoundError) as exc:
        raise SourceError(
            f'无法解析数据源连接串 `{dsn}`：{exc}。'
            '连接串需要带方言前缀，例如 sqlite:///./resource/app.db'
        ) from exc
    table_comment = ''
    try:
        inspector = inspect(engine)
        if table_name not in inspector.get_table_names():
            available = ', '.join(sorted(inspector.get_table_names())) or '（空库）'
            raise SourceError(f'表 `{table_name}` 不存在。当前库中可用表：{available}')

        try:
            table_comment = str((inspector.get_table_comment(table_name) or {}).get('text') or '').strip()
        except NotImplementedError:  # pragma: no cover - 部分方言不支持表注释
            table_comment = ''

        pk_columns = set(
            inspector.get_pk_constraint(table_name).get('constrained_columns') or []
        )
        unique_columns = {
            column
            for constraint in inspector.get_unique_constraints(table_name)
            for column in (constraint.get('column_names') or [])
        }
        indexed_columns = {
            column
            for index in inspector.get_indexes(table_name)
            for column in (index.get('column_names') or [])
        }

        fields: List[FieldSpec] = []
        for column in inspector.get_columns(table_name):
            fields.append(
                _field_from_column(
                    column,
                    primary_key=column['name'] in pk_columns,
                    unique=column['name'] in unique_columns,
                    index=column['name'] in indexed_columns,
                )
            )
    finally:
        engine.dispose()

    base = _strip_prefix(table_name) if app and table_name.startswith(f'{app}_') else table_name
    module_name = to_snake_case(base)
    spec = ModuleSpec(
        name=module_name,
        app=app,
        class_name=class_name or to_pascal_case(module_name),
        table_name=table_name,
        comment=comment or table_comment,
        path=path,
        router=router,
        fields=fields,
        source='table',
        with_timestamp=with_timestamp,
        with_soft_delete=with_soft_delete,
    )
    return spec


def _strip_prefix(table_name: str) -> str:
    """``system_area`` -> ``area``，去掉分组前缀以便推导类名。"""
    parts = table_name.split('_')
    return '_'.join(parts[1:]) if len(parts) > 1 else table_name


def _field_from_column(
    column: Dict[str, Any],
    *,
    primary_key: bool,
    unique: bool,
    index: bool,
) -> FieldSpec:
    sql_type = column.get('type')
    type_key = type(sql_type).__name__.upper()
    logical = SQLALCHEMY_TYPE_MAP.get(type_key, 'str')

    length = getattr(sql_type, 'length', None)
    precision = getattr(sql_type, 'precision', None)
    scale = getattr(sql_type, 'scale', None)

    if logical == 'str' and not length:
        length = 255

    nullable = bool(column.get('nullable', True))
    autoincrement = None
    if primary_key:
        reported = column.get('autoincrement')
        if reported in (None, 'auto'):
            # 方言未明确给出：整数主键按自增处理
            autoincrement = type_key in (
                'INTEGER', 'INT', 'BIGINT', 'BIGINTEGER', 'SMALLINT', 'SMALLINTEGER',
            )
        else:
            autoincrement = bool(reported)

    return FieldSpec(
        name=column['name'],
        type=logical,
        length=length,
        precision=precision,
        scale=scale,
        nullable=nullable,
        primary_key=primary_key,
        comment=str(column.get('comment') or '').strip(),
        index=index and not unique,
        unique=unique,
        autoincrement=autoincrement,
    )


# ---------------------------------------------------------------------------
# 4. 已有模型定义（AST 静态解析，不执行项目代码）
# ---------------------------------------------------------------------------

def model_spec(
    target: str,
    *,
    project_root: Optional[str] = None,
    app: Optional[str] = None,
    class_name: Optional[str] = None,
    comment: str = '',
    path: Optional[str] = None,
    router: Optional[str] = None,
) -> ModuleSpec:
    """解析项目里已有的 ``models.py``，据此生成模块描述。

    ``target`` 支持 ``apps.system.area.models.Area``、``apps/system/area/models.py:Area``
    与 ``apps/system/area/models.py`` 三种写法。
    """
    root = project_root or os.getcwd()
    file_path, wanted_class = resolve_model_target(target, root)
    classes = parse_model_file(file_path)

    if not classes:
        raise SourceError(f'`{file_path}` 里没有找到模型类')

    if wanted_class:
        if wanted_class not in classes:
            raise SourceError(
                f'`{file_path}` 中没有模型类 `{wanted_class}`，'
                f'可用：{", ".join(classes)}'
            )
        model_class = wanted_class
    else:
        model_class = next(iter(classes))

    parsed = classes[model_class]
    fields = [FieldSpec(**payload) for payload in parsed['fields']]

    spec = ModuleSpec(
        name=_module_name_from_path(file_path, root) or to_snake_case(parsed['table_name'] or model_class),
        app=app or _app_from_path(file_path, root),
        class_name=class_name or model_class,
        table_name=parsed['table_name'] or to_snake_case(model_class),
        comment=comment or parsed['comment'],
        path=path,
        router=router,
        fields=fields,
        source='model',
        with_timestamp=parsed['with_timestamp'],
        with_soft_delete=parsed['with_soft_delete'],
        extra_imports=parsed['extra_imports'],
    )
    spec._sync_pk_mixin()
    return spec


def resolve_model_target(target: str, project_root: str) -> Tuple[str, Optional[str]]:
    """把 ``--from-model`` 的写法解析成 ``(文件路径, 类名)``。"""
    if not target:
        raise SourceError('--from-model 需要指定模型位置')

    raw = target.strip()
    file_path: Optional[str] = None
    class_name: Optional[str] = None

    for separator in (':', '#'):
        if separator in raw:
            raw, _, class_name = raw.partition(separator)
            raw = raw.strip()
            class_name = class_name.strip() or None
            break

    candidate = raw if os.path.isabs(raw) else os.path.join(project_root, raw)
    if os.path.isfile(candidate):
        file_path = candidate
    elif os.path.isfile(candidate + '.py'):
        file_path = candidate + '.py'
    else:
        # 点分模块路径：apps.system.area.models[.Area]
        parts = raw.replace('/', '.').split('.')
        for index in range(len(parts) - 1, 0, -1):
            partial = os.path.join(project_root, *parts[:index]) + '.py'
            if os.path.isfile(partial):
                file_path = partial
                trailing = parts[index:]
                if trailing:
                    class_name = class_name or trailing[-1]
                break
        if file_path is None:
            package_init = os.path.join(project_root, *parts) + '.py'
            if os.path.isfile(package_init):
                file_path = package_init

    if file_path is None:
        raise SourceError(f'找不到模型文件：{target}')

    if not class_name:
        # 文件名若只是 models 包，取同目录同名 module；否则用文件名推类名
        stem = os.path.splitext(os.path.basename(file_path))[0]
        if stem not in ('models', '__init__', 'model'):
            class_name = None
    return file_path, class_name


def _app_from_path(file_path: str, project_root: str) -> Optional[str]:
    relative = os.path.relpath(file_path, project_root).replace(os.sep, '/')
    parts = relative.split('/')
    if len(parts) >= 4 and parts[0] == 'apps':
        return parts[1]
    return None


def _module_name_from_path(file_path: str, project_root: str) -> Optional[str]:
    """按目录结构推模块名：``apps/<app>/<module>/models.py`` -> ``module``。"""
    relative = os.path.relpath(file_path, project_root).replace(os.sep, '/')
    parts = relative.split('/')
    stem = os.path.splitext(parts[-1])[0]
    if stem in ('models', 'model', '__init__') and len(parts) >= 2:
        return to_snake_case(parts[-2])
    if stem in ('models', 'model', '__init__'):
        return None
    return to_snake_case(stem)


def parse_model_file(file_path: str) -> Dict[str, Dict[str, Any]]:
    """静态解析模型文件，返回 ``{类名: {...}}``。"""
    with open(file_path, encoding='utf-8') as handle:
        source = handle.read()

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SourceError(f'`{file_path}` 语法错误，无法解析：{exc}') from exc

    aliases = _collect_import_aliases(tree)
    result: Dict[str, Dict[str, Any]] = {}

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [_base_name(base) for base in node.bases]
        table_name = ''
        doc = ast.get_docstring(node) or ''
        fields: List[Dict[str, Any]] = []

        for stmt in node.body:
            target_name, value = _assignment(stmt)
            if target_name is None or value is None:
                continue
            if target_name == '__tablename__' and isinstance(value, ast.Constant):
                table_name = str(value.value)
                continue
            if target_name != '__schema__' and isinstance(value, ast.Call):
                payload = _field_from_call(value, aliases)
                if payload:
                    payload['name'] = target_name
                    fields.append(payload)

        if not fields:
            continue

        result[node.name] = {
            'table_name': table_name,
            'comment': doc.splitlines()[0].strip() if doc else '',
            'fields': fields,
            'with_timestamp': any('Timestamp' in base for base in bases),
            'with_soft_delete': any('SoftDelete' in base for base in bases),
            'extra_imports': [],
        }

    return result


def _collect_import_aliases(tree: ast.Module) -> Dict[str, str]:
    """收集 ``import ... as ...`` 与 ``from ... import ... as ...`` 的别名。"""
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split('.')[0]] = alias.name.split('.')[-1]
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
    return aliases


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return ''


def _assignment(stmt: ast.stmt) -> Tuple[Optional[str], Optional[ast.expr]]:
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        target = stmt.targets[0]
        if isinstance(target, ast.Name):
            return target.id, stmt.value
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return stmt.target.id, stmt.value
    return None, None


def _field_from_call(node: ast.Call, aliases: Dict[str, str]) -> Optional[Dict[str, Any]]:
    func_name = _base_name(node.func)
    if not func_name:
        return None
    resolved = aliases.get(func_name, func_name)
    if resolved not in BUILDER_TO_TYPE:
        return None

    logical = BUILDER_TO_TYPE[resolved]
    payload: Dict[str, Any] = {'type': logical}
    positional = list(node.args)

    if resolved == 'AutoPkField':
        # AutoPkField 内部自带 primary_key=True / autoincrement=True，需要显式还原
        payload['primary_key'] = True
        payload['autoincrement'] = True

    if resolved in LENGTH_BUILDERS and positional:
        length = _literal(positional.pop(0))
        if length:
            payload['length'] = length

    if resolved in ('EnumField', 'IntEnumField', 'StrEnumField') and positional:
        payload['enum_class'] = _base_name(positional.pop(0))

    keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
    for key, argument in keywords.items():
        if key == 'length':
            payload['length'] = _literal(argument)
        elif key == 'precision':
            payload['precision'] = _literal(argument)
        elif key == 'scale':
            payload['scale'] = _literal(argument)
        elif key == 'nullable':
            payload['nullable'] = bool(_literal(argument, True))
        elif key == 'primary_key':
            payload['primary_key'] = bool(_literal(argument, False))
        elif key == 'index':
            payload['index'] = bool(_literal(argument, False))
        elif key == 'unique':
            payload['unique'] = bool(_literal(argument, False))
        elif key == 'autoincrement':
            payload['autoincrement'] = _literal(argument)
        elif key == 'comment':
            payload['comment'] = str(_literal(argument, '') or '')
        elif key == 'default':
            payload['default'] = _unparse(argument)
        elif key == 'pk_type':
            payload['pk_type'] = _unparse(argument)

    return payload


def _literal(node: ast.expr, default: Any = None) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return default


def _unparse(node: ast.expr) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - 极端 AST 形态
        return ''


__all__ = [
    'SourceError',
    'empty_spec',
    'fields_spec',
    'table_spec',
    'model_spec',
    'discover_dsn',
    'parse_model_file',
    'resolve_model_target',
    'BUILDER_TO_TYPE',
]
