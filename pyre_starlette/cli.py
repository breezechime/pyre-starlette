"""pyre 命令行工具：项目脚手架与代码生成。

命令一览（``pyre -h`` 可查看完整别名表）::

    pyre new <name>              新建项目骨架          (n / init / i)
    pyre run                     启动服务              (r)
    pyre dev                     开发模式（自动重载）
    pyre make <kind> <name>      代码生成              (g / gen / mk)
    pyre list                    查看生成类型与模板     (ls / l)
    pyre eject <template>        导出模板              (e)
    pyre doctor                  项目自检              (d)
    pyre lsp install             安装语言服务（编辑器补全）

``make`` 的 ``<kind>`` 也支持顶层直接调用，例如 ``pyre make c article`` 与 ``pyre c article``
等价。生成来源由参数决定：给 ``-t/--table`` 走表反射，给 ``-m/--from-model`` 走模型解析，
给 ``-f/--fields`` 走内联字段，都不给则是空壳。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import unicodedata
from typing import List, Optional, Tuple

#: kind 名 -> (别名列表, 说明, 生成文件)
KIND_TABLE = (
    ('app',        ('a',),        '创建应用分组目录（apps/<name>/）',           ('__init__.py',)),
    ('module',     ('mod',),      '创建整套模块（6 个文件，推荐）',              None),
    ('model',      ('m',),        '创建模型 models.py',                         ('models.py',)),
    ('schema',     ('sc',),       '创建请求/返回对象 schema.py',                ('schema.py',)),
    ('service',    ('s',),        '创建业务 service.py',                        ('service.py',)),
    ('controller', ('c',),        '创建控制器 controller.py',                   ('controller.py',)),
    ('enums',      ('en',),       '创建枚举 enums.py',                          ('enums.py',)),
    ('crud',       ('cr',),       '按已有表生成整套 CRUD（需 -t/--table）',      None),
    ('sync',       ('sy',),       '按模型定义增量同步 schema.py（需 -m）',       ('schema.py',)),
)

KIND_NAMES = [name for name, _aliases, _help, _files in KIND_TABLE]
KIND_ALIASES = [alias for _name, aliases, _help, _files in KIND_TABLE for alias in aliases]
KIND_HELP = {name: help_text for name, _aliases, help_text, _files in KIND_TABLE}
KIND_FILE_MAP = {name: files for name, _aliases, _help, files in KIND_TABLE}

#: 生成文件 -> 说明，用于生成后的回执
FILE_DESCRIPTIONS = {
    '__init__.py': '模块包声明',
    'enums.py': '枚举定义',
    'models.py': 'ORM 模型',
    'schema.py': '请求 / 返回对象',
    'service.py': '业务逻辑',
    'controller.py': '控制器路由',
}

#: 默认路由变量（``模块:属性``）
DEFAULT_ROUTER = 'apps:api_router'
ADMIN_ROUTER = 'apps:admin_router'

#: 语言服务仓库（不在 PyPI 发布，直接从源码装）
LSP_REPO = 'https://github.com/breezechime/pyre-lsp.git'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='pyre',
        description='pyre 命令行工具：项目脚手架与代码生成',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_make_epilog(),
    )
    subparsers = parser.add_subparsers(dest='command', metavar='<command>')

    # ---- new ----
    new_parser = subparsers.add_parser(
        'new', aliases=['n', 'init', 'i'],
        help='新建项目骨架',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    new_parser.add_argument('project_name', help='项目名称（同时作为目录名）')
    new_parser.add_argument('-p', '--port', type=int, default=8000, help='服务端口')
    new_parser.add_argument('-d', '--dsn', default='sqlite:///./resource/app.db', help='默认数据源连接串')
    new_parser.add_argument('-o', '--output', default=None, help='输出根目录')
    new_parser.add_argument('-y', '--force', action='store_true', help='目录非空时也继续')
    new_parser.add_argument('-n', '--dry-run', action='store_true', help='只打印不写文件')

    # ---- run / dev ----
    run_parser = subparsers.add_parser(
        'run', aliases=['r'],
        help='启动服务',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    run_parser.add_argument('--host', default=None, help='监听地址（缺省取配置）')
    run_parser.add_argument('--port', type=int, default=None, help='监听端口（缺省取配置）')
    run_parser.add_argument('--app', default=None, help='应用模块，如 app:app / main:app')
    run_parser.add_argument('--no-reload', dest='reload', action='store_false', help='关闭自动重载')
    run_parser.set_defaults(reload=True)

    dev_parser = subparsers.add_parser('dev', help='开发模式（强制自动重载）')
    dev_parser.add_argument('--host', default=None, help='监听地址')
    dev_parser.add_argument('--port', type=int, default=None, help='监听端口')
    dev_parser.add_argument('--app', default=None, help='应用模块，如 app:app / main:app')

    # ---- make ----
    make_parser = subparsers.add_parser(
        'make', aliases=['g', 'gen', 'mk'],
        help='代码生成（子命令见下）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_make_epilog(),
    )
    make_subparsers = make_parser.add_subparsers(dest='kind', metavar='<kind>')
    for name, aliases, help_text, _files in KIND_TABLE:
        _add_kind_parser(make_subparsers, name, aliases, help_text)

    # ---- 顶层快捷：pyre c article ----
    for name, aliases, help_text, _files in KIND_TABLE:
        alias_help = f'{help_text}（≡ pyre make {name}）'
        _add_kind_parser(subparsers, name, aliases, alias_help)

    # ---- list ----
    list_parser = subparsers.add_parser(
        'list', aliases=['ls', 'l'],
        help='列出生成类型与内置模板',
    )
    list_parser.add_argument('what', nargs='?', choices=['kind', 'kinds', 'template', 'templates'],
                             default='kinds', help='要列出的内容')

    # ---- eject ----
    eject_parser = subparsers.add_parser(
        'eject', aliases=['e'],
        help='把内置模板导出到 ./templates 以便覆盖',
    )
    eject_parser.add_argument('template', help='模板相对路径，如 module/models.py')
    eject_parser.add_argument('-o', '--output', default=None, help='输出目录')

    # ---- doctor ----
    subparsers.add_parser('doctor', aliases=['d'], help='项目自检（目录、数据源、模块清单）')

    # ---- lsp ----
    lsp_parser = subparsers.add_parser(
        'lsp',
        help='安装 / 配置 pyre 语言服务（编辑器补全）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_lsp_epilog(),
    )
    lsp_subparsers = lsp_parser.add_subparsers(dest='lsp_action', metavar='<action>')

    lsp_install = lsp_subparsers.add_parser(
        'install',
        help='从 GitHub 安装 pyre-lsp',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    lsp_install.add_argument('-r', '--ref', default='main', help='Git 分支 / 标签 / 提交')
    lsp_install.add_argument('-u', '--upgrade', action='store_true', help='已安装时强制重装最新版')
    lsp_install.add_argument('-i', '--index', default='', help='pip 索引地址（缺省用 pip 全局配置）')
    lsp_install.add_argument('-n', '--dry-run', action='store_true', help='只打印命令，不执行安装')

    lsp_config = lsp_subparsers.add_parser(
        'config',
        help='打印编辑器配置片段',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    lsp_config.add_argument('-e', '--editor', choices=['vscode', 'jetbrains'], default='vscode',
                            help='目标编辑器')

    lsp_subparsers.add_parser('status', help='查看 pyre-lsp 是否已安装')

    # ---- 兼容旧命令 templates ----（保持 sync 的 nargs='?' 使 JSON 提取正常）
    templates_parser = subparsers.add_parser('templates', help=argparse.SUPPRESS)
    templates_parser.add_argument('templates_action', nargs='?', default=None, help=argparse.SUPPRESS)
    templates_parser.add_argument('template', nargs='?', default=None, help=argparse.SUPPRESS)

    return parser


def _add_kind_parser(subparsers, name: str, aliases, help_text: str) -> None:
    parser = subparsers.add_parser(
        name,
        aliases=list(aliases),
        help=help_text,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.set_defaults(kind=name)
    _add_generation_arguments(parser, name)


def _add_generation_arguments(parser: argparse.ArgumentParser, name: str) -> None:
    parser.add_argument(
        'name', nargs='?', default=None,
        help='模块 / 名称（给了 -t 或 -m 时可省略，从表或模型推断）',
    )
    parser.add_argument('-a', '--app', default=None, help='应用分组，生成到 apps/<app>/<name>/')
    parser.add_argument('-c', '--class', dest='class_name', default=None, help='类名（默认由名称推导）')
    parser.add_argument('-t', '--table', default=None, help='按数据库已有表生成')
    parser.add_argument('-m', '--from-model', dest='from_model', default=None,
                        help='按已有模型生成，如 apps/system/area/models.py:Area')
    parser.add_argument('-f', '--fields', default=None,
                        help='内联字段，如 "name:str:64!@#名称,age:int"')
    parser.add_argument('-d', '--dsn', default=None, help='数据源连接串（缺省读 resource/application*.toml）')
    parser.add_argument('-p', '--path', default=None, help='路由前缀（默认 /<app>/<name>）')
    parser.add_argument('-r', '--router', default=DEFAULT_ROUTER,
                        help='挂载用的路由变量（模块:属性），none 表示不挂载')
    parser.add_argument('--admin', action='store_true', help='挂到 admin_router（等价 -r apps:admin_router）')
    parser.add_argument('--comment', default=None, help='模块中文说明（用于注释与 OpenAPI summary）')
    parser.add_argument('-e', '--empty', action='store_true', help='强制空壳，忽略其它来源')
    parser.add_argument('--with-timestamp', action='store_true',
                        help='模型叠加 TimestampMixin（表反射默认不加）')
    parser.add_argument('--with-soft-delete', action='store_true', help='模型叠加 SoftDeleteMixin')
    parser.add_argument('-o', '--output', default=None, help='输出根目录（默认当前目录）')
    parser.add_argument('-y', '--force', action='store_true', help='覆盖已存在文件')
    parser.add_argument('-R', '--register', action='store_true',
                        help='把生成的控制器写入 apps/__init__.py')
    parser.add_argument('-n', '--dry-run', action='store_true', help='只预览不写文件')
    parser.add_argument('-v', '--verbose', action='store_true', help='预览时打印文件内容')


def _kind_head(name: str, aliases) -> str:
    return name if not aliases else f'{name} | {", ".join(aliases)}'


def _lsp_epilog() -> str:
    return '\n'.join([
        '语言服务（pyre-lsp）不在 PyPI 发布，直接从 GitHub 源码安装:',
        '',
        '  pyre lsp install                 安装 / 更新',
        '  pyre lsp install -r v0.1.0       指定分支、标签或提交',
        '  pyre lsp config -e vscode        打印 VS Code settings.json 片段',
        '  pyre lsp config -e jetbrains     打印 LSP4IJ 配置',
        '  pyre lsp status                  查看安装路径',
        '',
        '安装完成后把编辑器里的 serverPath 指向 `pyre lsp status` 给出的可执行文件。',
    ])


def _make_epilog() -> str:
    lines = ['生成类型 <kind>（顶层可直接使用，如 `pyre c article`）:', '']
    heads = [_kind_head(name, aliases) for name, aliases, _h, _f in KIND_TABLE]
    width = max(_width(head) for head in heads) + 2
    for head, (_name, _aliases, help_text, _files) in zip(heads, KIND_TABLE):
        lines.append(f'  {_pad(head, width)}{help_text}')
    lines.extend([
        '',
        '生成来源（按优先级）:',
        '  -t/--table <表名>      反射数据库已有表',
        '  -m/--from-model <模型> 解析项目里已有的 ORM 模型',
        '  -f/--fields <字段>     内联字段声明，如 "name:str:64!@#名称,age:int"',
        '  （都不给）             空壳：结构完整、字段留 TODO',
        '',
        '示例:',
        '  pyre new demo                      新建项目',
        '  pyre make module article -a content        空壳模块',
        '  pyre c article -a content -R               只生成控制器并写入注册表',
        '  pyre crud content_article -a content       按已有表生成整套 CRUD',
        '  pyre m article -f "name:str:64!@#标题,age:int"  按内联字段生成模型',
        '  pyre sy article -m apps/content/article/models.py  按模型增量同步 schema',
    ])
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    command = args.command
    try:
        if command in ('new', 'n', 'init', 'i'):
            handle_new(args)
        elif command in ('run', 'r'):
            handle_run(args)
        elif command == 'dev':
            args.reload = True
            handle_run(args)
        elif command in ('make', 'g', 'gen', 'mk'):
            if not getattr(args, 'kind', None):
                parser.parse_args(['make', '--help'])
                return
            handle_make(args)
        elif command in KIND_NAMES or command in KIND_ALIASES:
            handle_make(args)
        elif command in ('list', 'ls', 'l'):
            handle_list(args)
        elif command in ('eject', 'e'):
            handle_eject(args)
        elif command in ('doctor', 'd'):
            handle_doctor(args)
        elif command == 'lsp':
            handle_lsp(args)
        elif command == 'templates':
            handle_legacy_templates(args)
        else:
            parser.print_help()
    except (FileExistsError, FileNotFoundError, ValueError, RuntimeError) as error:
        print(f'错误: {error}', file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

def handle_new(args) -> None:
    from pyre_starlette.applications.code_generator.generators import ProjectGenerator

    generator = ProjectGenerator(
        project_name=args.project_name,
        project_root=args.output or os.getcwd(),
        port=args.port,
        dsn=args.dsn,
        force=args.force,
        dry_run=args.dry_run,
    )
    result = generator.generate()

    prefix = '[dry-run] ' if args.dry_run else ''
    print(f'{prefix}项目 {args.project_name} 已创建：')
    for path in result.written:
        print(f'  {_relative(path)}{"  " + _describe_project(path) if _describe_project(path) else ""}')
    if not args.dry_run:
        print()
        print('下一步:')
        print(f'  cd {args.project_name}')
        print('  pyre make module demo -a sample -R')
        print('  pyre run')


def _describe_project(path: str) -> str:
    name = os.path.basename(path)
    mapping = {
        'app.py': '应用入口',
        '__init__.py': '路由注册表',
        'application.toml': '公共配置',
        'application-dev.toml': '开发环境 / 数据源',
        'README.md': '项目说明',
    }
    return mapping.get(name, '')


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def handle_run(args) -> None:
    import uvicorn

    target = getattr(args, 'app', None)
    if not target:
        if os.path.exists('app.py'):
            target = 'app:app'
        elif os.path.exists('main.py'):
            target = 'main:app'
        else:
            print('错误: 未找到 app.py 或 main.py，可用 --app 显式指定', file=sys.stderr)
            sys.exit(1)

    options = {'reload': bool(getattr(args, 'reload', True))}
    if getattr(args, 'host', None):
        options['host'] = args.host
    else:
        options['host'] = '127.0.0.1'
    if getattr(args, 'port', None):
        options['port'] = args.port
    else:
        options['port'] = 8000

    uvicorn.run(target, **options)


# ---------------------------------------------------------------------------
# make
# ---------------------------------------------------------------------------

def handle_make(args) -> None:
    kind = args.kind
    if kind == 'sync':
        _handle_sync(args)
        return

    if kind == 'crud':
        # `pyre crud <表名>`：位置参数就是表名，没给 -t 时直接用它
        if not args.table:
            args.table = args.name
            args.name = None
        if not args.table:
            raise ValueError('crud 需要表名，如：pyre crud system_area -a system')

    if kind == 'app':
        _handle_app(args)
        return

    spec = build_spec(args)
    files = KIND_FILE_MAP.get(kind)
    _generate(spec, args, files)


def build_spec(args):
    """按参数决定生成来源。"""
    from pyre_starlette.applications.code_generator import sources

    common = {
        'app': args.app,
        'class_name': args.class_name,
        'comment': args.comment or '',
        'path': args.path,
        'router': None if str(args.router).lower() in ('none', 'no', '-') else args.router,
    }
    if args.admin and args.router == DEFAULT_ROUTER:
        common['router'] = ADMIN_ROUTER

    if args.table and not args.empty:
        return sources.table_spec(
            args.table,
            dsn=args.dsn,
            project_root=os.getcwd(),
            with_timestamp=args.with_timestamp,
            with_soft_delete=args.with_soft_delete,
            **common,
        )

    name = args.name
    if not name and not args.from_model:
        raise ValueError('缺少名称，例如：pyre make module article')
    if args.empty and not name:
        raise ValueError('空壳模式需要名称，例如：pyre make module article -e')

    table_name = args.table
    if table_name is None and args.app and name and args.from_model is None and args.fields is None:
        table_name = f'{args.app}_{name}'

    if args.empty:
        return sources.empty_spec(
            name,
            table_name=table_name,
            with_soft_delete=args.with_soft_delete,
            **common,
        )

    if args.from_model:
        return sources.model_spec(
            args.from_model,
            project_root=os.getcwd(),
            **common,
        )

    if args.fields:
        return sources.fields_spec(
            name,
            args.fields,
            table_name=table_name,
            with_soft_delete=args.with_soft_delete,
            **common,
        )

    return sources.empty_spec(
        name,
        table_name=table_name,
        with_soft_delete=args.with_soft_delete,
        **common,
    )


def _handle_app(args) -> None:
    from pyre_starlette.applications.code_generator.generators import AppGenerator

    generator = AppGenerator(
        args.name,
        project_root=args.output or os.getcwd(),
        comment=args.comment or '',
        force=args.force,
        dry_run=args.dry_run,
    )
    result = generator.generate()
    prefix = '[dry-run] ' if args.dry_run else ''
    print(f'{prefix}应用分组 {args.name} 已创建：')
    for path in result.written:
        print(f'  {_relative(path)}')


def _resolve_files(spec, args, files) -> Tuple[Tuple[str, ...], List[str]]:
    """单文件生成时补齐磁盘上缺失的硬依赖，返回 (文件元组, 自动补齐说明)。

    单独生成 ``models.py`` 时它仍会 ``from .enums import ...``，单独生成任何文件时
    模块目录都得是包，否则生成结果导入即报错。
    """
    from pyre_starlette.applications.code_generator.generators import MODULE_FILES

    selected = list(files or MODULE_FILES)
    module_path = os.path.join(args.output or os.getcwd(), *spec.module_dir.split('/'))
    added: List[str] = []

    def _missing(name: str) -> bool:
        return name not in selected and not os.path.isfile(os.path.join(module_path, name))

    if _missing('__init__.py'):
        selected.insert(0, '__init__.py')
        added.append('__init__.py')

    if 'models.py' in selected and spec.needed_enums and _missing('enums.py'):
        selected.append('enums.py')
        added.append('enums.py')

    return tuple(selected), added


def _generate(spec, args, files) -> None:
    from pyre_starlette.applications.code_generator.generators import (
        MODULE_FILES,
        ModuleGenerator,
        register_controller,
    )

    files, added = _resolve_files(spec, args, files)

    generator = ModuleGenerator(
        spec,
        project_root=args.output or os.getcwd(),
        files=files or MODULE_FILES,
        force=args.force,
        dry_run=args.dry_run,
    )
    result = generator.generate()

    prefix = '[dry-run] ' if args.dry_run else ''
    source_label = {
        'empty': '空壳',
        'fields': f'内联字段 {len(spec.fields)} 个',
        'table': f'表 {spec.table_name}',
        'model': '已有模型',
    }.get(spec.source, spec.source)

    print(f'{prefix}{spec.class_name} 模块（{source_label}） -> {spec.module_dir}/')
    if added:
        print(f'  自动补齐硬依赖：{", ".join(added)}')
    if result.app_init:
        print(f'  {"__init__.py".ljust(16)}应用分组声明（{_relative(result.app_init)}）')
    for path in result.written:
        description = FILE_DESCRIPTIONS.get(os.path.basename(path), '')
        print(f'  {os.path.basename(path).ljust(16)}{description}')
        if args.verbose:
            _echo_text(result.rendered.get(path) if args.dry_run else _read(path))
    for path in result.skipped:
        print(f'  跳过 {os.path.basename(path)}（已存在，需要覆盖请加 -y）')

    if args.register and not args.dry_run:
        if not _has_controller(args.output or os.getcwd(), spec.module_dir, files):
            print('  提示：当前只生成 '
                  + ', '.join(files or MODULE_FILES)
                  + '，没有 controller.py，跳过 -R 注册')
            return
        line = register_controller(
            args.output or os.getcwd(),
            spec.module_dir,
            spec.controller_class,
        )
        if line:
            print(f'  已写入注册表：{line}')
        else:
            print('  注册表已是期望内容，未改动')
    elif not args.register and not args.dry_run and _has_controller(args.output or os.getcwd(), spec.module_dir, files):
        print(f'  提示：把 {spec.controller_class} import 到 apps/__init__.py，或用 -R 自动写入')


def _has_controller(project_root: str, module_dir: str, files) -> bool:
    """本次生成或磁盘上是否已经有 controller.py。"""
    from pyre_starlette.applications.code_generator.generators import MODULE_FILES

    if 'controller.py' in (files or MODULE_FILES):
        return True
    return os.path.isfile(os.path.join(project_root, *module_dir.split('/'), 'controller.py'))


def _handle_sync(args) -> None:
    from pyre_starlette.applications.code_generator import sources
    from pyre_starlette.applications.code_generator.sync import sync_schema

    if not args.from_model:
        raise ValueError('sync 需要 -m/--from-model 指定模型，如：'
                         'pyre sy article -m apps/content/article/models.py')

    project_root = os.getcwd()
    spec = sources.model_spec(
        args.from_model,
        project_root=project_root,
        app=args.app,
        class_name=args.class_name,
        comment=args.comment or '',
        path=args.path,
        router=None,
    )
    if args.name:
        spec.name = args.name

    model_path, _cls = sources.resolve_model_target(args.from_model, project_root)
    schema_path = os.path.join(os.path.dirname(model_path), 'schema.py')

    report = sync_schema(spec, schema_path, dry_run=args.dry_run)
    prefix = '[dry-run] ' if args.dry_run else ''
    print(f'{prefix}同步 schema：{_relative(schema_path)}')
    for line in report.summary_lines():
        print(f'  {line}')
    if args.verbose:
        print(f'  模型字段 {len(spec.fields)} 个：'
              + ', '.join(item.name for item in spec.fields))


# ---------------------------------------------------------------------------
# list / eject / doctor
# ---------------------------------------------------------------------------

def handle_list(args) -> None:
    from pyre_starlette.applications.code_generator import PyreCodeGenerator

    what = args.what
    if what in ('kinds', 'kind'):
        print('生成类型:')
        heads = [_kind_head(name, aliases) for name, aliases, _h, _f in KIND_TABLE]
        width = max(_width(head) for head in heads) + 2
        for head, (_name, aliases, help_text, files) in zip(heads, KIND_TABLE):
            output = ', '.join(files) if files else '6 个文件'
            print(f'  {_pad(head, width)}{help_text}   -> {output}')
        return

    generator = PyreCodeGenerator()
    print(f'默认模板目录: {generator.default_template_dir}')
    custom_dir = generator.get_custom_template_dir()
    print(f'自定义模板目录: {custom_dir or "（未创建，可用 pyre eject 生成）"}')
    print('内置模板:')
    for name in generator.list_templates():
        print(f'  {name}')


def handle_eject(args) -> None:
    from pyre_starlette.applications.code_generator import PyreCodeGenerator

    generator = PyreCodeGenerator()
    try:
        target = generator.eject_template(args.template, args.output)
    except FileNotFoundError:
        print(f'错误: 模板不存在：{args.template}', file=sys.stderr)
        print('可用模板见 `pyre list templates`', file=sys.stderr)
        sys.exit(1)
    print(f'模板导出成功: {target}')


def handle_doctor(args) -> None:
    from pyre_starlette.applications.code_generator import PyreCodeGenerator
    from pyre_starlette.applications.code_generator.sources import discover_dsn

    root = os.getcwd()
    print(f'项目根目录: {root}')

    apps_dir = os.path.join(root, 'apps')
    if os.path.isdir(apps_dir):
        print('  ✓ apps/ 存在')
    else:
        print('  ✗ 未找到 apps/，请确认在项目根目录执行')

    init_file = os.path.join(apps_dir, '__init__.py')
    print(f'  {"✓" if os.path.isfile(init_file) else "✗"} apps/__init__.py'
          f'{"（含 api_router）" if os.path.isfile(init_file) and "api_router" in _read(init_file) else ""}')

    dsn = discover_dsn(root)
    if dsn:
        print(f'  ✓ 数据源: {_mask(dsn)}')
    else:
        print('  ✗ 未发现数据源（resource/application*.toml 里没有 [pyre.datasource].url）')

    generator = PyreCodeGenerator()
    print(f'  ✓ 内置模板 {len(generator.list_templates())} 个')
    custom_dir = generator.get_custom_template_dir()
    if custom_dir:
        print(f'  ✓ 自定义模板目录: {custom_dir}')

    modules = _discover_modules(apps_dir)
    if modules:
        print(f'模块（{len(modules)} 个）:')
        for module in modules:
            print(f'  {module}')
    else:
        print('  暂无业务模块（pyre make module <name> -a <分组>）')


def handle_lsp(args) -> None:
    """语言服务：从 GitHub 安装 pyre-lsp，并给出编辑器配置。"""
    action = getattr(args, 'lsp_action', None)
    if action == 'install':
        _lsp_install(args)
    elif action == 'config':
        _lsp_config(args)
    elif action == 'status':
        _lsp_status()
    else:
        print('用法: pyre lsp install | config | status')
        print('  安装: pyre lsp install [-r <ref>] [-u]')
        print('  配置: pyre lsp config [-e vscode|jetbrains]')
        print('  状态: pyre lsp status')


def _lsp_install(args) -> None:
    package = f'git+{LSP_REPO}@{args.ref}' if args.ref else f'git+{LSP_REPO}'
    cmd = [sys.executable, '-m', 'pip', 'install']
    if args.upgrade:
        cmd.append('--upgrade')
    if args.index:
        cmd += ['-i', args.index]
    cmd.append(package)

    print('安装 pyre-lsp（编辑器语言服务）')
    print(f'  来源: {package}')
    print(f'  命令: {" ".join(cmd)}')

    if args.dry_run:
        print('\n未执行（--dry-run）。')
        return

    try:
        result = subprocess.run(cmd)
    except OSError as error:
        raise RuntimeError(f'无法调用 pip: {error}') from error
    if result.returncode != 0:
        raise RuntimeError('安装失败，请检查网络、git 是否可用，或改用 -i 指定镜像源')

    path = lsp_executable()
    print('\n安装完成')
    if path:
        print(f'  可执行文件: {path}')
        print('  下一步: pyre lsp config -e vscode  # 生成编辑器配置')
    else:
        print('  未在 PATH 中找到 pyre-lsp，可能是 pip 安装目录不在 PATH。')
        print('  可在编辑器配置里改用: python -m pyre_lsp')


def lsp_executable() -> str:
    """返回 pyre-lsp 可执行文件路径，找不到返回空串。"""
    found = shutil.which('pyre-lsp')
    if found:
        return found
    scripts = os.path.dirname(sys.executable)
    for name in ('pyre-lsp.exe', 'pyre-lsp'):
        candidate = os.path.join(scripts, name)
        if os.path.isfile(candidate):
            return candidate
    return ''


def _lsp_status() -> None:
    path = lsp_executable()
    if path:
        print('pyre-lsp 已安装')
        print(f'  可执行文件: {path}')
        print(f'  回退命令  : {sys.executable} -m pyre_lsp')
    else:
        print('pyre-lsp 未安装')
        print('  安装: pyre lsp install')


def _lsp_config(args) -> None:
    path = lsp_executable()
    server = path or f'{sys.executable} -m pyre_lsp'

    if args.editor == 'vscode':
        snippet = {'pyreLsp.serverPath': path or ''}
        if not path:
            snippet = {'pyreLsp.serverPath': '', 'pyreLsp.pythonPath': sys.executable}
        print('VS Code / Cursor —— 写入 .vscode/settings.json:')
        print(json.dumps(snippet, ensure_ascii=False, indent=2))
        print('\n也可以直接安装仓库里的扩展：pyre_lsp/vscode/')
    else:
        print('IntelliJ / PyCharm —— LSP4IJ 里新建 User-defined Language Server:')
        print(f'  Command : {path or sys.executable}')
        print(f'  Arguments: {"" if path else "-m pyre_lsp"}')
        print('  Working directory: $PROJECT_DIR$')
        print('\n完整步骤见 pyre-lsp 仓库 README 的 LSP4IJ 一节。')

    if not path:
        print('\n提示: 未检测到 pyre-lsp，先执行 pyre lsp install')

    print(f'\n当前语言服务命令: {server}')


def handle_legacy_templates(args) -> None:
    """兼容旧命令 ``pyre templates list`` / ``pyre templates eject <tpl>``。"""
    action = getattr(args, 'templates_action', None)
    if action in ('list', 'ls', 'l'):
        handle_list(argparse.Namespace(what='templates'))
    elif action == 'eject':
        template = getattr(args, 'template', None)
        if not template:
            print('错误: 未知的模板操作', file=sys.stderr)
            sys.exit(1)
        handle_eject(argparse.Namespace(template=template, output=None))
    else:
        print('错误: 未知的模板操作', file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# 输出辅助
# ---------------------------------------------------------------------------

def _relative(path: str) -> str:
    try:
        return os.path.relpath(path, os.getcwd()).replace(os.sep, '/')
    except ValueError:  # pragma: no cover - 跨盘符
        return path


def _width(text: str) -> int:
    """终端显示宽度：东亚宽字符按 2 列计。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + ' ' * max(0, width - _width(text))


def _read(path: str) -> str:
    try:
        with open(path, encoding='utf-8') as handle:
            return handle.read()
    except OSError:
        return ''


def _mask(dsn: str) -> str:
    if '://' not in dsn:
        return dsn
    scheme, _, rest = dsn.partition('://')
    if '@' not in rest:
        return dsn
    credentials, _, host = rest.rpartition('@')
    user = credentials.split(':', 1)[0]
    return f'{scheme}://{user}:***@{host}'


def _echo_text(text: str) -> None:
    for line in (text or '').splitlines():
        print(f'      | {line}')


def _discover_modules(apps_dir: str) -> List[str]:
    found: List[str] = []
    for root, dirs, files in os.walk(apps_dir):
        dirs[:] = [item for item in dirs if not item.startswith(('_', '.'))]
        if 'models.py' in files and 'controller.py' in files:
            rel = os.path.relpath(root, os.path.dirname(apps_dir)).replace(os.sep, '/')
            found.append(rel)
    return sorted(found)


if __name__ == '__main__':
    main()
