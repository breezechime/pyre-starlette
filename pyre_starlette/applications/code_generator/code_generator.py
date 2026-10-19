"""向后兼容层。

新代码请直接用 :mod:`~pyre_starlette.applications.code_generator.sources`
（构造 :class:`~pyre_starlette.applications.code_generator.spec.ModuleSpec`）与
:mod:`~pyre_starlette.applications.code_generator.generators`（渲染文件）。

本模块仅保留旧类名，便于已有脚本平滑迁移。
"""
from __future__ import annotations

import os
from typing import List, Optional

from . import to_pascal_case, to_snake_case
from .generators import (
    KIND_FILES,
    MODULE_FILES,
    AppGenerator,
    ModuleGenerator,
    ProjectGenerator,
)
from .spec import FieldSpec, ModuleSpec
from .sources import empty_spec, table_spec

#: 旧版生成器的默认挂载点
DEFAULT_ROUTER = 'apps:api_router'

__all__ = [
    'PyreProjectCodeGenerator',
    'PyreAppCodeGenerator',
    'PyreModuleCodeGenerator',
    'PyreControllerCodeGenerator',
    'PyreServiceCodeGenerator',
    'PyreModelCodeGenerator',
    'PyreSchemaCodeGenerator',
    'PyreVoCodeGenerator',
    'PyreTableCodeGenerator',
    'ModuleSpec',
    'FieldSpec',
    'MODULE_FILES',
    'KIND_FILES',
]


class _BaseCompat:
    """旧版生成器的公共外壳。"""

    kind = 'module'

    def __init__(self, app_name: Optional[str] = None, project_root: Optional[str] = None):
        self.app_name = app_name
        self.project_root = project_root or os.getcwd()

    def _files(self) -> tuple:
        return KIND_FILES.get(self.kind, MODULE_FILES)

    def _generate(self, spec: ModuleSpec) -> List[str]:
        generator = ModuleGenerator(spec, project_root=self.project_root, files=self._files())
        result = generator.generate()
        if result.written:
            return result.written
        # 文件已存在且含手写内容时会被跳过；旧接口返回的是「目标路径」，这里保持一致
        return [generator.target_path(name) for name in self._files()]


class PyreProjectCodeGenerator:
    """旧版：生成项目骨架。"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root or os.getcwd()

    def generate(self, project_name: str) -> str:
        generator = ProjectGenerator(project_name, project_root=self.project_root)
        generator.generate()
        return os.path.join(self.project_root, project_name)


class PyreAppCodeGenerator:
    """旧版：创建应用分组目录。"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root or os.getcwd()

    def generate(self, app_name: str) -> str:
        generator = AppGenerator(app_name, project_root=self.project_root)
        generator.generate()
        return os.path.join(self.project_root, 'apps', to_snake_case(app_name))


class PyreModuleCodeGenerator(_BaseCompat):
    """整套模块（6 个文件）。"""

    kind = 'module'

    def generate(self, name: str, **kwargs) -> List[str]:
        spec = empty_spec(
            name,
            app=self.app_name,
            class_name=kwargs.get('class_name'),
            table_name=kwargs.get('table_name'),
            comment=kwargs.get('comment') or '',
            router=kwargs.get('router', DEFAULT_ROUTER),
        )
        return self._generate(spec)


class PyreControllerCodeGenerator(_BaseCompat):
    """只生成 controller.py。"""

    kind = 'controller'

    def generate(self, name: str, class_name: Optional[str] = None, file_name: Optional[str] = None) -> str:
        spec = empty_spec(name, app=self.app_name, class_name=class_name, router=DEFAULT_ROUTER)
        return self._generate(spec)[0]


class PyreServiceCodeGenerator(_BaseCompat):
    """只生成 service.py。"""

    kind = 'service'

    def generate(self, name: str, class_name: Optional[str] = None, file_name: Optional[str] = None) -> str:
        spec = empty_spec(name, app=self.app_name, class_name=class_name)
        return self._generate(spec)[0]


class PyreModelCodeGenerator(_BaseCompat):
    """只生成 models.py。"""

    kind = 'model'

    def generate(
        self,
        name: str,
        table_name: Optional[str] = None,
        class_name: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> str:
        spec = empty_spec(name, app=self.app_name, class_name=class_name, table_name=table_name)
        return self._generate(spec)[0]


class PyreSchemaCodeGenerator(_BaseCompat):
    """只生成 schema.py。"""

    kind = 'schema'

    def generate(self, name: str, class_name: Optional[str] = None, file_name: Optional[str] = None) -> str:
        spec = empty_spec(name, app=self.app_name, class_name=class_name)
        return self._generate(spec)[0]


class PyreVoCodeGenerator(PyreSchemaCodeGenerator):
    """旧版 ``vo`` 概念，等价于 ``schema``。"""


class PyreTableCodeGenerator(_BaseCompat):
    """按已有表生成整套 CRUD。"""

    kind = 'crud'

    def generate(self, table_name: str, class_name: Optional[str] = None) -> List[str]:
        spec = table_spec(
            table_name,
            project_root=self.project_root,
            app=self.app_name,
            class_name=class_name or to_pascal_case(table_name),
            router=DEFAULT_ROUTER,
        )
        return self._generate(spec)
