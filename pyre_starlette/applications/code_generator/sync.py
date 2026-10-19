"""模型 → ``schema.py`` 增量同步。

读取 ORM 模型定义，把模型里新增的字段补进 ``schema.py`` 的
``XxxParams`` / ``XxxResponse``；已有字段与手写代码原样保留，只报告不删除。
"""
from __future__ import annotations

import ast
import os
from typing import Dict, List, Optional, Set, Tuple

from .spec import FieldSpec, ModuleSpec, schema_import_lines

#: 需要补字段的 schema 类后缀
SYNC_SUFFIXES = ('Params', 'Response')

#: 与模型无关、由模板自带的基础字段
BUILTIN_FIELDS = {'id', 'page', 'page_size', 'count', 'data'}

#: 判定「标准库 import」用的模块名，用于保持 import 分组顺序
STDLIB_MODULES = {
    'abc', 'base64', 'collections', 'dataclasses', 'datetime', 'decimal', 'enum',
    'functools', 'hashlib', 'io', 'itertools', 'json', 'logging', 'math', 'os',
    'pathlib', 're', 'sys', 'time', 'typing', 'uuid',
}


class SyncReport:
    """同步结果。"""

    def __init__(self, schema_path: str):
        self.schema_path = schema_path
        self.added: Dict[str, List[str]] = {}
        self.existing: Dict[str, List[str]] = {}
        #: schema 里有、模型里已经没了的字段（只提示，不删除）
        self.stale: List[str] = []
        #: 目标类不存在，无法同步
        self.missing_classes: List[str] = []
        self.imports_added: List[str] = []

    @property
    def changed(self) -> bool:
        return bool(self.added or self.imports_added)

    @property
    def added_count(self) -> int:
        return sum(len(names) for names in self.added.values())

    def summary_lines(self) -> List[str]:
        lines: List[str] = []
        if self.imports_added:
            lines.append(f'补充 import：{", ".join(self.imports_added)}')
        for class_name, names in self.added.items():
            lines.append(f'{class_name} 新增 {len(names)} 个字段：{", ".join(names)}')
        if not self.added and not self.imports_added:
            lines.append('无需改动，schema 已与模型一致')
        for class_name in self.missing_classes:
            lines.append(f'（跳过）{class_name} 不存在，未同步')
        if self.stale:
            lines.append(
                '（仅提示，未删除）以下字段在模型中已不存在：' + ', '.join(self.stale)
            )
        return lines


def sync_schema(
    spec: ModuleSpec,
    schema_path: str,
    *,
    dry_run: bool = False,
) -> SyncReport:
    """把模型字段增量同步到 ``schema.py``。"""
    report = SyncReport(schema_path)
    if not os.path.isfile(schema_path):
        raise FileNotFoundError(f'找不到 schema 文件：{schema_path}')

    with open(schema_path, encoding='utf-8') as handle:
        source = handle.read()

    tree = ast.parse(source)
    classes = _collect_classes(tree)
    lines = source.splitlines()

    model_fields = {item.name: item for item in spec.fields}
    declared_names: Set[str] = set()
    #: (插入行号, 类名, 待插入字段) —— 先全部算完再自下而上插入，避免行号漂移
    pending: List[Tuple[int, str, List[FieldSpec]]] = []

    for suffix in SYNC_SUFFIXES:
        class_name = f'{spec.class_name}{suffix}'
        if class_name not in classes:
            report.missing_classes.append(class_name)
            continue
        node = classes[class_name]
        declared = _declared_fields(node)
        declared_names |= declared

        additions = [
            item
            for name, item in model_fields.items()
            if name not in declared and name not in BUILTIN_FIELDS
        ]
        if not additions:
            report.existing[class_name] = sorted(declared)
            continue

        pending.append((_insert_position(node, lines), class_name, additions))

    for insert_at, class_name, additions in sorted(pending, key=lambda item: item[0], reverse=True):
        lines[insert_at:insert_at] = [f'    {item.schema_line()}' for item in additions]
        report.added[class_name] = [item.name for item in additions]

    report.stale = sorted(declared_names - set(model_fields) - BUILTIN_FIELDS)

    updated = '\n'.join(lines)
    if not updated.endswith('\n'):
        updated += '\n'
    updated, added_imports = _ensure_imports(updated, _required_imports(model_fields))
    report.imports_added = added_imports

    if report.changed and not dry_run:
        with open(schema_path, 'w', encoding='utf-8') as handle:
            handle.write(updated)

    return report


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------

def _collect_classes(tree: ast.Module) -> Dict[str, ast.ClassDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


def _declared_fields(node: ast.ClassDef) -> Set[str]:
    names: Set[str] = set()
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _insert_position(node: ast.ClassDef, lines: List[str]) -> int:
    """返回新字段应插入的行号（在类体最后一个语句之后）。"""
    body = [stmt for stmt in node.body if not _is_docstring(stmt)]
    if not body:
        return node.lineno
    last = body[-1]
    end = getattr(last, 'end_lineno', None) or last.lineno
    return end


def _is_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _required_imports(scope: Dict[str, FieldSpec]) -> List[str]:
    """按同步进来的字段推导需要的 import。"""
    return schema_import_lines(list(scope.values()))


def _ensure_imports(source: str, required: List[str]) -> Tuple[str, List[str]]:
    """补上缺失的顶层 import，返回 (新源码, 新增的 import 行)。

    ``from typing import Any`` 这类会优先合并进已有的 ``from typing import ...`` 行，
    只有同模块没有现成 import 时才新起一行。
    """
    if not required:
        return source, []

    lines = source.splitlines()
    added: List[str] = []

    for import_line in required:
        if _covered(lines, import_line):
            continue
        if _merge_from_import(lines, import_line):
            added.append(import_line)
            continue
        lines.insert(_insert_index(lines, import_line), import_line)
        added.append(import_line)

    text = '\n'.join(lines)
    if source.endswith('\n') and not text.endswith('\n'):
        text += '\n'
    return text, added


def _import_block_end(lines: List[str]) -> int:
    """返回顶层 import 区块的结束行号。"""
    end = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('import ') or stripped.startswith('from '):
            end = index + 1
    return end


def _insert_index(lines: List[str], import_line: str) -> int:
    """按「标准库 import → 标准库 from → 第三方」的分组惯例定位插入行。"""
    end = _import_block_end(lines)
    last_plain = last_stdlib_from = None
    first_from = None
    for index, line in enumerate(lines[:end]):
        stripped = line.strip()
        if stripped.startswith('import '):
            last_plain = index
        elif stripped.startswith('from '):
            if first_from is None:
                first_from = index
            module = stripped.split()[1]
            if module in STDLIB_MODULES:
                last_stdlib_from = index

    if import_line.startswith('import '):
        if last_plain is not None:
            return last_plain + 1
        return first_from if first_from is not None else end

    module = import_line.split()[1] if len(import_line.split()) > 1 else ''
    if module in STDLIB_MODULES:
        if last_stdlib_from is not None:
            return last_stdlib_from + 1
        if last_plain is not None:
            return last_plain + 1
        return first_from if first_from is not None else end
    return end


def _import_names(import_line: str, module: str) -> List[str]:
    """从 ``from module import a, b as c`` 里取出被导入的名字。"""
    body = import_line.split(' import ', 1)[1]
    body = body.split('#', 1)[0]
    return [part.split(' as ')[0].strip() for part in body.split(',') if part.strip()]


def _covered(lines: List[str], import_line: str) -> bool:
    """已有 import 是否已经覆盖了这条需求。"""
    for line in lines:
        if line.strip() == import_line:
            return True

    if import_line.startswith('import '):
        for name in _plain_import_names(import_line):
            if not any(name in _plain_import_names(line.strip())
                       for line in lines if line.strip().startswith('import ')):
                return False
        return True

    module, _, _names = import_line.partition(' import ')
    module = module.replace('from ', '').strip()
    wanted = _import_names(import_line, module)
    for name in wanted:
        found = any(
            name in _import_names(line.strip(), module)
            for line in lines
            if line.strip().startswith(f'from {module} import')
        )
        if not found:
            return False
    return True


def _plain_import_names(line: str) -> List[str]:
    body = line.split('import ', 1)[1] if 'import ' in line else ''
    body = body.split('#', 1)[0]
    return [part.split(' as ')[0].strip() for part in body.split(',') if part.strip()]


def _merge_from_import(lines: List[str], import_line: str) -> bool:
    """把 ``from m import a`` 合并进已有的 ``from m import b`` 行；成功返回 True。"""
    if not import_line.startswith('from '):
        return False
    module, _, _names = import_line.partition(' import ')
    module = module.replace('from ', '').strip()
    prefix = f'from {module} import'

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        code, comment = _split_comment(stripped)
        names = [part.split(' as ')[0].strip()
                 for part in code[len(prefix):].split(',') if part.strip()]
        merged = sorted(set(names) | set(_import_names(import_line, module)))
        if merged == names:
            return True
        lines[index] = f'{prefix} {", ".join(merged)}{comment}'
        return True
    return False


def _split_comment(line: str) -> Tuple[str, str]:
    index = line.find(' #')
    if index == -1:
        return line.rstrip(), ''
    return line[:index].rstrip(), f' {line[index:].lstrip()}'


__all__ = ['SyncReport', 'sync_schema', 'SYNC_SUFFIXES']
