"""代码生成的中间描述层：字段与模块。

生成器不直接拼字符串，而是先把「表结构 / 模型定义 / 内联字段 / 空壳」统一收敛成
``ModuleSpec``，再由模板渲染。这样四种来源可以共用同一套模板。
"""
from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, List, Optional

from . import to_camel_case, to_pascal_case, to_snake_case

# ---------------------------------------------------------------------------
# 类型表
# ---------------------------------------------------------------------------

#: 逻辑类型 -> 渲染所需信息
#: builder    sqlalchemy_db 中的字段构造函数
#: python     schema.py 中使用的 Python 类型
#: jsonable   是否需要在 schema 中 import Decimal / datetime 等
FIELD_TYPES: Dict[str, Dict[str, Any]] = {
    'int': {
        'builder': 'IntegerField',
        'python': 'int',
    },
    'bigint': {
        'builder': 'BigIntegerField',
        'python': 'int',
    },
    'smallint': {
        'builder': 'SmallIntegerField',
        'python': 'int',
    },
    'str': {
        'builder': 'StringField',
        'python': 'str',
        'length': 255,
    },
    'text': {
        'builder': 'TextField',
        'python': 'str',
    },
    'mediumtext': {
        'builder': 'MediumtextField',
        'python': 'str',
    },
    'bool': {
        'builder': 'BooleanField',
        'python': 'bool',
    },
    'float': {
        'builder': 'FloatField',
        'python': 'float',
    },
    'decimal': {
        'builder': 'DecimalField',
        'python': 'Decimal',
        'precision': 10,
        'scale': 2,
        'decimal': True,
    },
    'date': {
        'builder': 'DateField',
        'python': 'date',
        'datetime': True,
    },
    'datetime': {
        'builder': 'DateTimeField',
        'python': 'datetime',
        'datetime': True,
    },
    'time': {
        'builder': 'TimeField',
        'python': 'time',
        'datetime': True,
    },
    'json': {
        'builder': 'JSONField',
        'python': 'Any',
        'typing': True,
    },
    'bytes': {
        'builder': 'BinaryField',
        'python': 'bytes',
    },
}

#: 类型别名，用于 ``--fields`` 的内联简写
TYPE_ALIASES: Dict[str, str] = {
    'int': 'int',
    'integer': 'int',
    'i': 'int',
    'bigint': 'bigint',
    'long': 'bigint',
    'smallint': 'smallint',
    'str': 'str',
    'string': 'str',
    'varchar': 'str',
    's': 'str',
    'text': 'text',
    'mediumtext': 'mediumtext',
    'bool': 'bool',
    'boolean': 'bool',
    'b': 'bool',
    'float': 'float',
    'f': 'float',
    'double': 'float',
    'decimal': 'decimal',
    'numeric': 'decimal',
    'd': 'decimal',
    'date': 'date',
    'datetime': 'datetime',
    'timestamp': 'datetime',
    'time': 'time',
    'json': 'json',
    'jsonb': 'json',
    'j': 'json',
    'bytes': 'bytes',
    'blob': 'bytes',
    'binary': 'bytes',
    'enum': 'enum',
    'e': 'enum',
    'intenum': 'intenum',
    'strenum': 'strenum',
}

#: 反射时 SQLAlchemy 类型名 -> 逻辑类型
SQLALCHEMY_TYPE_MAP: Dict[str, str] = {
    'BIGINT': 'bigint',
    'BIGINTEGER': 'bigint',
    'INTEGER': 'int',
    'INT': 'int',
    'SMALLINTEGER': 'smallint',
    'SMALLINT': 'smallint',
    'TINYINT': 'smallint',
    'MEDIUMINT': 'int',
    'VARCHAR': 'str',
    'STRING': 'str',
    'CHAR': 'str',
    'NCHAR': 'str',
    'NVARCHAR': 'str',
    'TEXT': 'text',
    'CLOB': 'text',
    'MEDIUMTEXT': 'mediumtext',
    'LONGTEXT': 'mediumtext',
    'TINYTEXT': 'text',
    'BOOLEAN': 'bool',
    'BOOL': 'bool',
    'FLOAT': 'float',
    'REAL': 'float',
    'DOUBLE': 'float',
    'DOUBLE_PRECISION': 'float',
    'NUMERIC': 'decimal',
    'DECIMAL': 'decimal',
    'DECIMAL128': 'decimal',
    'DATE': 'date',
    'DATETIME': 'datetime',
    'TIMESTAMP': 'datetime',
    'TIME': 'time',
    'JSON': 'json',
    'JSONB': 'json',
    'BLOB': 'bytes',
    'LARGEBINARY': 'bytes',
    'BYTEA': 'bytes',
    'VARBINARY': 'bytes',
}

#: EnumField 相关的逻辑类型（需要显式枚举类）
ENUM_TYPES = ('enum', 'intenum', 'strenum')

#: 逻辑枚举类型 -> ``enum`` 模块中的基类名
ENUM_BASES = {'enum': 'Enum', 'intenum': 'IntEnum', 'strenum': 'StrEnum'}

#: 可自增的整数类型
INTEGER_TYPES = ('int', 'bigint', 'smallint')

RESERVED_FIELD_NAMES = {'self', 'cls'}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def py_str(value: str) -> str:
    """把值渲染成 Python 单引号字符串字面量。"""
    text = str(value).replace('\\', '\\\\').replace("'", "\\'")
    text = text.replace('\n', '\\n').replace('\r', '\\r')
    return f"'{text}'"


def safe_identifier(name: str) -> str:
    """把任意字符串变成合法的小写标识符。"""
    text = re.sub(r'[^0-9a-zA-Z_]+', '_', str(name or '')).strip('_').lower()
    if not text:
        text = 'field'
    if text[0].isdigit():
        text = f'_{text}'
    if keyword.iskeyword(text):
        text = f'{text}_'
    return text


def resolve_type(type_name: str) -> str:
    """解析内联类型别名，未知则报错。"""
    key = str(type_name or '').strip().lower()
    if key not in TYPE_ALIASES:
        raise ValueError(
            f'未知字段类型 `{type_name}`，可用：'
            + ', '.join(sorted(set(TYPE_ALIASES.values())))
        )
    return TYPE_ALIASES[key]


# ---------------------------------------------------------------------------
# 字段
# ---------------------------------------------------------------------------

@dataclass
class FieldSpec:
    """一个字段的完整描述。"""

    name: str
    type: str = 'str'
    length: Optional[int] = None
    nullable: bool = True
    primary_key: bool = False
    comment: str = ''
    default: Optional[str] = None
    server_default: Optional[str] = None
    index: bool = False
    unique: bool = False
    autoincrement: Optional[bool] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    enum_class: Optional[str] = None
    pk_type: Optional[str] = None
    extra: Dict[str, Any] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = safe_identifier(self.name)
        meta = FIELD_TYPES.get(self.type, FIELD_TYPES['str'])
        if self.length is None and meta.get('length'):
            self.length = meta['length']
        if self.precision is None and meta.get('precision'):
            self.precision = meta['precision']
        if self.scale is None and meta.get('scale'):
            self.scale = meta['scale']
        if self.comment is None:
            self.comment = ''
        # 主键必然非空；整数主键默认自增
        if self.primary_key:
            self.nullable = False
            if self.autoincrement is None and self.type in INTEGER_TYPES:
                self.autoincrement = True

    # -- 查询辅助 --
    @property
    def is_enum(self) -> bool:
        return self.type in ENUM_TYPES

    @property
    def python_type(self) -> str:
        if self.is_enum:
            return self.enum_class or 'str'
        return FIELD_TYPES.get(self.type, FIELD_TYPES['str'])['python']

    @property
    def schema_python_type(self) -> str:
        """``schema.py`` 里使用的类型：枚举降级为基础类型，避免依赖 ORM 枚举。

        ``EnumField`` 按成员名存取，所以普通枚举与 ``StrEnumField`` 用 ``str``；
        ``IntEnumField`` 按成员值存取，用 ``int``。
        """
        if self.is_enum:
            return 'int' if self.type == 'intenum' else 'str'
        return FIELD_TYPES.get(self.type, FIELD_TYPES['str'])['python']

    # -- 渲染：models.py --
    def model_expr(self) -> str:
        """渲染字段右侧的构造函数调用。"""
        if self.is_enum:
            return self._enum_expr()
        if self.primary_key and self.autoincrement and self.type in INTEGER_TYPES:
            return self._auto_pk_expr()

        meta = FIELD_TYPES.get(self.type, FIELD_TYPES['str'])
        builder = meta['builder']
        args: List[str] = []

        if builder == 'StringField' and self.length:
            args.append(str(self.length))
        if builder == 'DecimalField':
            args.append(f'precision={self.precision}')
            args.append(f'scale={self.scale}')

        args.extend(self._common_kwargs())
        return f'models.{builder}({", ".join(args)})'

    def _auto_pk_expr(self) -> str:
        """自增主键统一用 ``AutoPkField``（内部会把 BigInteger 在 SQLite 下降级为 INTEGER）。"""
        args: List[str] = []
        if self.pk_type and not self.pk_type.endswith('AUTO'):
            args.append(f'pk_type={self.pk_type}')
        if self.default is not None:
            args.append(f'default={self.default}')
        if self.comment:
            args.append(f'comment={py_str(self.comment)}')
        return f'models.AutoPkField({", ".join(args)})'

    def _enum_expr(self) -> str:
        enum_name = self.enum_class or to_pascal_case(self.name)
        builder = {'enum': 'EnumField', 'intenum': 'IntEnumField', 'strenum': 'StrEnumField'}[self.type]
        args = [enum_name]
        if self.type == 'strenum' and self.length and self.length != 32:
            args.append(f'length={self.length}')
        args.extend(self._common_kwargs())
        return f'models.{builder}({", ".join(args)})'

    def _common_kwargs(self) -> List[str]:
        kwargs: List[str] = []
        if self.primary_key:
            kwargs.append('primary_key=True')
        if self.autoincrement is not None:
            kwargs.append(f'autoincrement={self.autoincrement}')
        if not self.nullable and not self.primary_key:
            kwargs.append('nullable=False')
        if self.default is not None:
            kwargs.append(f'default={self.default}')
        if self.server_default is not None:
            kwargs.append(f'server_default={self.server_default}')
        if self.index and not self.primary_key:
            kwargs.append('index=True')
        if self.unique and not self.primary_key:
            kwargs.append('unique=True')
        if self.comment:
            kwargs.append(f'comment={py_str(self.comment)}')
        kwargs.extend(f'{key}={value}' for key, value in self.extra.items())
        return kwargs

    def model_line(self) -> str:
        """渲染 ``models.py`` 中的一行字段声明。"""
        return f'{self.name} = {self.model_expr()}'

    # -- 渲染：schema.py --
    def schema_line(self, *, optional: bool = True, description: bool = True) -> str:
        """渲染 ``schema.py`` 中的一行字段声明。"""
        py_type = self.schema_python_type
        if self.nullable or optional:
            annotation = f'Optional[{py_type}]'
            default = 'None' if self.nullable else self.default or 'None'
        else:
            annotation = py_type
            default = self.default or '...'

        field_args: List[str] = [default]
        if description and self.comment:
            field_args.append(f'description={py_str(self.comment)}')
        if self.length and self.type == 'str':
            field_args.append(f'max_length={self.length}')
        return f'{self.name}: {annotation} = Field({", ".join(field_args)})'

    # -- 渲染：enums.py --
    def requires_enum(self) -> bool:
        return self.is_enum and not self.enum_class

    def enum_member_name(self) -> str:
        return to_pascal_case(self.name)

    @property
    def enum_base(self) -> str:
        """``enums.py`` 中的枚举基类名（``Enum`` / ``IntEnum`` / ``StrEnum``）。"""
        return ENUM_BASES.get(self.type, 'Enum')

    @property
    def enum_placeholder(self) -> str:
        """空枚举的占位成员声明。

        没有成员的枚举无法作为 ``EnumField`` 使用（任何取值都会报
        ``LookupError``），因此生成一个占位成员保证代码开箱可运行。

        取值与 ``EnumField`` / ``IntEnumField`` / ``StrEnumField`` 的存取方式一致：
        ``EnumField`` 按成员名存取，另两者按成员值存取。
        """
        if self.type == 'intenum':
            return 'UNKNOWN = 0'
        if self.type == 'strenum':
            return "UNKNOWN = 'unknown'"
        return "UNKNOWN = 'UNKNOWN'"


def field_from_inline(token: str) -> FieldSpec:
    """解析 ``--fields`` 里的单个字段声明。

    语法：``name:type[:length|:precision,scale][!][=default]``

    * ``!``          —— 非空（``nullable=False``）
    * ``@``          —— 主键（``primary_key=True``）
    * ``?``          —— 显式可空（默认即如此）
    * ``#注释``      —— 列注释
    * ``=默认值``    —— Python 侧默认值（原样写入）

    示例::

        name:str:64!@#区域名称
        lng:decimal:10,6!#
        is_enable:bool=True
    """
    raw = token.strip()
    if not raw:
        raise ValueError('字段声明不能为空')

    comment = ''
    if '#' in raw:
        raw, comment = raw.split('#', 1)
        comment = comment.strip()

    default: Optional[str] = None
    if '=' in raw:
        raw, default = raw.split('=', 1)
        default = default.strip()

    nullable = True
    primary_key = False
    flags = set(re.findall(r'[!@?]', raw))
    raw = re.sub(r'[!@?]', '', raw)
    if '!' in flags:
        nullable = False
    if '@' in flags:
        primary_key = True

    parts = [part for part in raw.split(':') if part != '']
    if not parts:
        raise ValueError(f'字段声明缺少名称：{token}')
    name = parts[0].strip()
    type_name = parts[1].strip() if len(parts) > 1 else 'str'
    resolved = resolve_type(type_name)

    length = None
    precision = None
    scale = None
    if len(parts) > 2 and parts[2].strip():
        size = parts[2].strip()
        if ',' in size:
            head, _, tail = size.partition(',')
            precision = int(head)
            scale = int(tail)
        elif resolved == 'decimal':
            precision = int(size)
        else:
            length = int(size)

    return FieldSpec(
        name=name,
        type=resolved,
        length=length,
        precision=precision,
        scale=scale,
        nullable=nullable,
        primary_key=primary_key,
        comment=comment,
        default=default,
    )


def schema_import_lines(fields: List[FieldSpec]) -> List[str]:
    """按字段推导 ``schema.py`` 需要的 import（不含第三方）。

    ``date`` / ``datetime`` / ``time`` 使用 ``from datetime import ...``，
    枚举类型已降级为 ``str``，不需要额外 import。
    """
    names = {item.schema_python_type for item in fields}
    lines: List[str] = []
    datetime_names = sorted(name for name in names if name in ('date', 'datetime', 'time'))
    if datetime_names:
        lines.append(f'from datetime import {", ".join(datetime_names)}')
    if 'Decimal' in names:
        lines.append('from decimal import Decimal')
    lines.append('from typing import Any, Optional' if 'Any' in names else 'from typing import Optional')
    return lines


def parse_fields(text: Optional[str]) -> List[FieldSpec]:
    """解析 ``--fields`` 参数。

    字段之间用 ``,`` / ``;`` / 换行分隔；``decimal:12,2`` 里的逗号属于尺寸，
    会自动与前一字段合并，因此两种写法都成立::

        --fields "name:str:64!#名称,price:decimal:12,2!#价格"
        --fields "name:str:64!#名称;price:decimal:12,2!#价格"
    """
    if not text:
        return []

    normalized = re.sub(r'[;\n]+', ',', text)
    tokens = [token.strip() for token in normalized.split(',') if token.strip()]

    merged: List[str] = []
    for token in tokens:
        if merged and re.fullmatch(r'\d+\s*[!@?]*(#.*)?', token):
            merged[-1] = f'{merged[-1]},{token}'
        else:
            merged.append(token)

    return [field_from_inline(token) for token in merged]


# ---------------------------------------------------------------------------
# 模块
# ---------------------------------------------------------------------------

@dataclass
class ModuleSpec:
    """一个业务模块的完整描述。"""

    name: str
    app: Optional[str] = None
    class_name: Optional[str] = None
    table_name: Optional[str] = None
    comment: str = ''
    path: Optional[str] = None
    router: Optional[str] = None
    fields: List[FieldSpec] = dataclass_field(default_factory=list)
    source: str = 'empty'
    with_pk_mixin: bool = True
    with_timestamp: bool = True
    with_soft_delete: bool = False
    extra_imports: List[str] = dataclass_field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = to_snake_case(str(self.name).strip())
        if not self.name:
            raise ValueError('模块名不能为空')
        self.class_name = self.class_name or to_pascal_case(self.name)
        self.table_name = self.table_name or self.name
        self.comment = self.comment or self.class_name
        self.app = to_snake_case(self.app) if self.app else None
        if self.path is None:
            segments = [segment for segment in (self.app, self.name) if segment]
            self.path = '/' + '/'.join(segments)
        self._sync_pk_mixin()
        self._sync_builtin_columns()

    def _sync_pk_mixin(self) -> None:
        """字段里已有主键时不再叠加 ``PkMixin``。"""
        if any(item.primary_key for item in self.fields):
            self.with_pk_mixin = False

    def _sync_builtin_columns(self) -> None:
        """表里已经把内置列反射成字段时，不再叠加对应 Mixin。"""
        names = {item.name for item in self.fields}
        if 'create_time' in names or 'update_time' in names:
            self.with_timestamp = False
        if 'delete_time' in names:
            self.with_soft_delete = False

    # -- 路径 --
    @property
    def module_dir(self) -> str:
        """相对项目根的模块目录（POSIX 分隔符）。"""
        parts = ['apps']
        if self.app:
            parts.append(self.app)
        parts.append(self.name)
        return '/'.join(parts)

    @property
    def package(self) -> str:
        """点分模块路径。"""
        return self.module_dir.replace('/', '.')

    @property
    def router_module(self) -> str:
        """``--router apps:api_router`` 中的模块部分。"""
        return (self.router or '').split(':')[0]

    @property
    def router_attr(self) -> str:
        """``--router apps:api_router`` 中的属性部分。"""
        return self.router.split(':')[-1] if self.router else ''

    @property
    def controller_class(self) -> str:
        return f'{self.class_name}Controller'

    @property
    def service_class(self) -> str:
        return f'{self.class_name}Service'

    # -- 字段渲染 --
    @property
    def bases(self) -> str:
        """``models.Model`` 等基类组合。"""
        bases = ['models.Model']
        if self.with_pk_mixin:
            bases.append('models.PkMixin')
        if self.with_timestamp:
            bases.append('models.TimestampMixin')
        if self.with_soft_delete:
            bases.append('models.SoftDeleteMixin')
        return ', '.join(bases)

    @property
    def comment_literal(self) -> str:
        return py_str(self.comment)

    @property
    def model_fields(self) -> List[str]:
        return [item.model_line() for item in self.fields]

    @property
    def schema_fields(self) -> List[str]:
        return [item.schema_line() for item in self.fields]

    @property
    def schema_param_fields(self) -> List[str]:
        """``XxxParams`` 的字段：恒带 ``id``，其余字段排除同名冲突。"""
        lines = ["id: Optional[int] = Field(None, description='序号')"]
        lines.extend(item.schema_line() for item in self.fields if item.name != 'id')
        return lines

    @property
    def schema_response_fields(self) -> List[str]:
        lines = ["id: Optional[int] = Field(None, description='序号')"]
        lines.extend(item.schema_line() for item in self.fields if item.name != 'id')
        return lines

    @property
    def svc_fields(self) -> List[FieldSpec]:
        return list(self.fields)

    @property
    def needed_enums(self) -> List[FieldSpec]:
        return [item for item in self.fields if item.requires_enum()]

    @property
    def enum_import_line(self) -> str:
        """``models.py`` 需要的枚举 import。

        既包含本次要在 ``enums.py`` 里生成的枚举，也包含模型原本就引用的枚举类。
        """
        names = {item.enum_member_name() for item in self.needed_enums}
        names |= {item.enum_class for item in self.fields if item.is_enum and item.enum_class}
        return f'from .enums import {", ".join(sorted(names))}' if names else ''

    @property
    def schema_imports(self) -> List[str]:
        """``schema.py`` 需要的 import，按固定顺序输出。"""
        lines = schema_import_lines(self.fields)
        lines.append('from pydantic import BaseModel, ConfigDict, Field')
        lines.extend(self.extra_imports)
        return lines


    # -- 序列化 --
    def to_context(self) -> Dict[str, Any]:
        return {'spec': self}
