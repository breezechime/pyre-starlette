"""生成器：把 :class:`~.spec.ModuleSpec` 渲染成项目文件。"""
from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import PyreCodeGenerator, to_pascal_case, to_snake_case
from .spec import ModuleSpec

#: 一个标准业务模块包含的文件（顺序即生成顺序）
MODULE_FILES: Tuple[str, ...] = (
    '__init__.py',
    'enums.py',
    'models.py',
    'schema.py',
    'service.py',
    'controller.py',
)

#: 文件名 -> 模板
FILE_TEMPLATES: Dict[str, str] = {
    '__init__.py': 'module/__init__.py.j2',
    'enums.py': 'module/enums.py.j2',
    'models.py': 'module/models.py.j2',
    'schema.py': 'module/schema.py.j2',
    'service.py': 'module/service.py.j2',
    'controller.py': 'module/controller.py.j2',
}

#: 各生成类型对应的文件集合
KIND_FILES: Dict[str, Tuple[str, ...]] = {
    'module': MODULE_FILES,
    'model': ('models.py',),
    'schema': ('schema.py',),
    'service': ('service.py',),
    'controller': ('controller.py',),
    'enums': ('enums.py',),
    'crud': MODULE_FILES,
}


class GenerationResult:
    """一次生成的结果。"""

    def __init__(self):
        self.written: List[str] = []
        self.skipped: List[str] = []
        self.registered: Optional[str] = None
        #: ``apps/<分组>/__init__.py``，本次新建时才有值
        self.app_init: Optional[str] = None
        #: 目标路径 -> 渲染内容（``dry_run`` 时用于预览）
        self.rendered: Dict[str, str] = {}

    @property
    def created(self) -> int:
        return len(self.written)

    def __bool__(self) -> bool:
        return bool(self.written) or bool(self.registered)


class ModuleGenerator(PyreCodeGenerator):
    """按模块描述生成文件。

    ``files`` 决定生成哪些文件（默认整套），``force`` 决定是否覆盖已存在文件，
    ``dry_run`` 只渲染不落盘，便于预览。
    """

    def __init__(
        self,
        spec: ModuleSpec,
        project_root: Optional[str] = None,
        files: Optional[Sequence[str]] = None,
        force: bool = False,
        dry_run: bool = False,
    ):
        super().__init__(project_root)
        self.spec = spec
        self.files = tuple(files or MODULE_FILES)
        self.force = force
        self.dry_run = dry_run
        self.result = GenerationResult()

    # -- 路径 --
    @property
    def target_dir(self) -> str:
        return os.path.join(self.project_root, *self.spec.module_dir.split('/'))

    def target_path(self, file_name: str) -> str:
        return os.path.join(self.target_dir, file_name)

    # -- 生成 --
    def generate(self) -> GenerationResult:
        self._ensure_app_package()
        context = self.build_context()

        for file_name in self.files:
            template = FILE_TEMPLATES[file_name]
            target = self.target_path(file_name)
            content = self.render_template(template, **context)

            if self.dry_run:
                self.result.written.append(target)
                self.result.rendered[target] = content
                continue

            if os.path.exists(target) and not self.force:
                existing = self._read(target)
                if existing == content:
                    self.result.skipped.append(target)
                    continue
                if not self._is_untouched(existing):
                    self.result.skipped.append(target)
                    continue

            self.write_file(target, content)
            self.result.written.append(target)

        return self.result

    def build_context(self) -> Dict[str, object]:
        return self.spec.to_context()

    def _ensure_app_package(self) -> None:
        """``apps/<分组>/`` 需要有自己的 ``__init__.py``。"""
        if not self.spec.app:
            return
        target = os.path.join(self.project_root, 'apps', self.spec.app, '__init__.py')
        if os.path.exists(target):
            return
        self.result.app_init = target
        if self.dry_run:
            return
        self.write_file(target, f'"""{to_pascal_case(self.spec.app)} 应用分组。"""\n')

    @staticmethod
    def _read(path: str) -> str:
        try:
            with open(path, encoding='utf-8') as handle:
                return handle.read()
        except OSError:
            return ''

    @staticmethod
    def _is_untouched(content: str) -> bool:
        """判断文件是否仍是生成时的原样（只含 TODO 与结构）。"""
        stripped = content.strip()
        if not stripped:
            return True
        body = re.sub(r'"""[\s\S]*?"""', '', content, count=1).strip()
        for line in body.splitlines():
            line = line.rstrip()
            if not line or line.startswith('#'):
                continue
            return False
        return True


class ProjectGenerator(PyreCodeGenerator):
    """生成新项目骨架。"""

    def __init__(
        self,
        project_name: str,
        project_root: Optional[str] = None,
        port: int = 8000,
        dsn: str = 'sqlite:///./resource/app.db',
        force: bool = False,
        dry_run: bool = False,
    ):
        super().__init__(project_root)
        self.project_name = project_name
        self.port = port
        self.dsn = dsn
        self.force = force
        self.dry_run = dry_run

    @property
    def target_dir(self) -> str:
        return os.path.join(self.project_root, self.project_name)

    def generate(self) -> GenerationResult:
        result = GenerationResult()
        if os.path.exists(self.target_dir) and os.listdir(self.target_dir) and not self.force:
            raise FileExistsError(f'目录 {self.project_name} 已存在且非空，用 -y/--force 覆盖')

        context = {
            'project_name': self.project_name,
            'port': self.port,
            'dsn': self.dsn,
        }
        files = (
            ('project/app.py.j2', 'app.py'),
            ('project/apps/__init__.py.j2', 'apps/__init__.py'),
            ('project/resource/application.toml.j2', 'resource/application.toml'),
            ('project/resource/application-dev.toml.j2', 'resource/application-dev.toml'),
            ('project/README.md.j2', 'README.md'),
        )
        for template, relative in files:
            target = os.path.join(self.target_dir, relative)
            if self.dry_run:
                result.written.append(target)
                continue
            self.render_and_write(template, target, **context)
            result.written.append(target)
        return result


class AppGenerator(PyreCodeGenerator):
    """创建应用分组目录（``apps/<name>/``）。"""

    def __init__(
        self,
        app_name: str,
        project_root: Optional[str] = None,
        comment: str = '',
        force: bool = False,
        dry_run: bool = False,
    ):
        super().__init__(project_root)
        self.app_name = to_snake_case(app_name)
        self.comment = comment or f'{to_pascal_case(app_name)} 应用分组'
        self.force = force
        self.dry_run = dry_run

    @property
    def target_dir(self) -> str:
        return os.path.join(self.project_root, 'apps', self.app_name)

    def generate(self) -> GenerationResult:
        result = GenerationResult()
        target = os.path.join(self.target_dir, '__init__.py')
        if self.dry_run:
            result.written.append(target)
            return result
        self.write_file(target, f'"""{self.comment}。"""\n')
        result.written.append(target)
        return result


def register_controller(
    project_root: str,
    module_dir: str,
    controller_class: str,
    init_file: Optional[str] = None,
) -> Optional[str]:
    """把控制器 import 写进 ``apps/__init__.py``，让路由被挂载。

    已经存在同名 import 时不做任何改动，返回 ``None``。
    """
    init_file = init_file or os.path.join(project_root, 'apps', '__init__.py')
    if not os.path.isfile(init_file):
        return None

    parts = [part for part in re.split(r'[/\\]', module_dir) if part]
    if parts and parts[0] == 'apps':
        parts = parts[1:]
    relative = '.'.join(parts)
    import_line = f'from .{relative}.controller import {controller_class}  # noqa'

    with open(init_file, encoding='utf-8') as handle:
        content = handle.read()

    if _already_registered(content, relative, controller_class):
        return None

    if content and not content.endswith('\n'):
        content += '\n'
    content += f'{import_line}\n'

    with open(init_file, 'w', encoding='utf-8') as handle:
        handle.write(content)
    return import_line


def _already_registered(content: str, relative: str, controller_class: str) -> bool:
    """``apps/__init__.py`` 里是否已经有该控制器的 import。

    只看真实代码行（忽略注释与文档字符串），避免模板里的示例注释造成误判。
    """
    for line in content.splitlines():
        code = line.split('#', 1)[0].strip()
        if not code.startswith('from '):
            continue
        module, _, names = code.partition(' import ')
        if not module.endswith(f'.{relative}.controller'):
            continue
        if controller_class in [part.strip() for part in names.split(',')]:
            return True
    return False


__all__ = [
    'MODULE_FILES',
    'FILE_TEMPLATES',
    'KIND_FILES',
    'GenerationResult',
    'ModuleGenerator',
    'ProjectGenerator',
    'AppGenerator',
    'register_controller',
]
