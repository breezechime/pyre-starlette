import os
import re
import shutil
from typing import Any, Callable, Dict, List, Optional

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, Template


def _split_words(value: str) -> List[str]:
    """把任意命名风格拆成单词列表。"""
    text = str(value or '').strip()
    if not text:
        return []
    text = re.sub(r'[\s\-./]+', '_', text)
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', text)
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', text)
    return [word for word in text.split('_') if word]


def to_pascal_case(value: str) -> str:
    """``system_area`` / ``systemArea`` -> ``SystemArea``"""
    return ''.join(word[:1].upper() + word[1:].lower() for word in _split_words(value))


def to_camel_case(value: str) -> str:
    """``system_area`` -> ``systemArea``（与 :func:`to_pascal_case` 兼容保留）。"""
    words = _split_words(value)
    if not words:
        return ''
    return words[0].lower() + ''.join(word[:1].upper() + word[1:].lower() for word in words[1:])


def to_snake_case(value: str) -> str:
    """``SystemArea`` / ``system-area`` -> ``system_area``"""
    return '_'.join(word.lower() for word in _split_words(value))


def to_kebab_case(value: str) -> str:
    """``SystemArea`` -> ``system-area``"""
    return '-'.join(word.lower() for word in _split_words(value))


class TemplatePath:
    """模板路径配置"""

    def __init__(self, template_path: str, output_path: str, context: Optional[Dict[str, Any]] = None):
        self.template_path = template_path
        self.output_path = output_path
        self.context = context or {}


class PyreCodeGenerator:
    """代码生成器基类"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root or os.getcwd()
        self.default_template_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'templates'
        )
        self.loader = self.create_loader()
        self.env = Environment(
            loader=self.loader,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def get_custom_template_dir(self) -> Optional[str]:
        """获取用户自定义模板目录"""
        templates_dir = os.path.join(self.project_root, 'templates')
        if os.path.exists(templates_dir):
            return templates_dir
        return None

    def create_loader(self):
        """创建模板加载器，支持自定义模板覆盖"""
        loaders = []
        custom_dir = self.get_custom_template_dir()
        if custom_dir:
            loaders.append(FileSystemLoader(custom_dir))
        loaders.append(FileSystemLoader(self.default_template_dir))
        if len(loaders) > 1:
            return ChoiceLoader(loaders)
        return loaders[0]

    def get_template_list(self) -> List[TemplatePath]:
        """获取模板列表配置"""
        return []

    def generate_from_template_list(
        self,
        template_list: List[TemplatePath],
        base_context: Optional[Dict[str, Any]] = None,
        base_dir: Optional[str] = None
    ) -> None:
        """根据模板列表生成文件"""
        base_context = base_context or {}
        base_dir = base_dir or self.project_root

        for template_path_config in template_list:
            if not template_path_config.template_path or not template_path_config.output_path:
                continue

            output_path = template_path_config.output_path
            if callable(output_path):
                output_path = output_path()

            if not os.path.isabs(output_path):
                output_path = os.path.join(base_dir, output_path)

            merged_context = {**base_context, **template_path_config.context}
            self.render_and_write(template_path_config.template_path, output_path, **merged_context)

    def get_template(self, template_path: str) -> Template:
        """获取模板"""
        return self.env.get_template(template_path)

    def render_template(self, template_path: str, **kwargs) -> str:
        """渲染模板"""
        template = self.get_template(template_path)
        return template.render(**kwargs)

    def write_file(self, file_path: str, content: str, encoding: str = 'utf-8') -> None:
        """写入文件"""
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(file_path, 'w', encoding=encoding) as f:
            f.write(content)

    def render_and_write(self, template_path: str, file_path: str, **kwargs) -> None:
        """渲染模板并写入文件"""
        content = self.render_template(template_path, **kwargs)
        self.write_file(file_path, content)

    def eject_template(self, template_name: str, target_dir: Optional[str] = None) -> str:
        """把内置模板复制到用户模板目录，便于覆盖定制。"""
        name = template_name if template_name.endswith('.j2') else f'{template_name}.j2'
        src_path = os.path.join(self.default_template_dir, name)
        if not os.path.isfile(src_path):
            raise FileNotFoundError(name)

        target_dir = target_dir or os.path.join(self.project_root, 'templates')
        dst_path = os.path.join(target_dir, name)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        shutil.copy2(src_path, dst_path)
        return dst_path

    def list_templates(self) -> List[str]:
        """列出内置模板的相对路径。"""
        names: List[str] = []
        for root, _dirs, files in os.walk(self.default_template_dir):
            for file in files:
                if file.endswith('.j2'):
                    rel_path = os.path.relpath(os.path.join(root, file), self.default_template_dir)
                    names.append(rel_path.replace(os.sep, '/'))
        return sorted(names)


def get_current_app_name() -> Optional[str]:
    """获取当前app名称（``apps`` 下只有一个分组时返回它）。"""
    current_dir = os.getcwd()
    apps_dir = os.path.join(current_dir, 'apps')

    if not os.path.exists(apps_dir):
        return None

    subdirs = [
        d for d in os.listdir(apps_dir)
        if os.path.isdir(os.path.join(apps_dir, d)) and not d.startswith('_')
    ]

    if len(subdirs) == 1:
        return subdirs[0]
    return None


__all__ = [
    'PyreCodeGenerator',
    'TemplatePath',
    'to_pascal_case',
    'to_camel_case',
    'to_snake_case',
    'to_kebab_case',
    'get_current_app_name',
]
