import logging
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, ConfigDict, Field, AliasChoices

from .constants import LOGGING_FORMAT, LOGGING_PLAIN_FORMAT, LOG_COLORS, LOGGING_NAME
from .openapi.models import License, Contact, Server, Tag


class ConnectConfig(BaseModel):
    """连接实体"""

    model_config = ConfigDict(from_attributes=True, extra='allow')

    url: Optional[str] = Field(default=None, description="连接URL")
    engine: Optional[str] = Field(default=None, description="数据库引擎")
    host: Optional[str] = Field(default=None, description="主机")
    port: Optional[int] = Field(default=None, description="端口")
    username: Optional[str] = Field(default=None, description="账户名")
    password: Optional[str] = Field(default=None, description="密码")
    database: Optional[str] = Field(default=None, description="数据库")
    charset: Optional[str] = Field(default='utf8mb4', description="编码")

    def __bool__(self):
        return not self.is_none()

    def is_none(self) -> bool:
        """检查是是否为空"""
        return self.url is None and self.host is None

    def build_url(self) -> str:
        """构建URL"""
        if self.url:
            return self.url

        port = self.port or 3306
        return (
            f"{self.engine}://{self.username}:{self.password}@{self.host}:{port}/{self.database or ''}"
            f"{'?charset=' + self.charset if self.charset else ''}"
        )


class DatabaseConnectConfig(ConnectConfig):
    """数据库连接配置"""

    echo: Optional[bool] = Field(default=None, description='输出sql')
    pool_pre_ping: Optional[bool] = Field(default=None, description='连接池预连接')
    pool_size: Optional[int] = Field(default=None, description='连接池大小')
    max_overflow: Optional[int] = Field(default=None, description='最大溢出连接数')
    pool_recycle: Optional[int] = Field(default=None, description='连接池回收时间')
    pool_timeout: Optional[int] = Field(default=None, description='连接池超时时间')
    options: Optional[dict] = Field(default=None, description='额外参数')
    session_options: Optional[dict] = Field(default=None, description='会话额外参数')


class DatasourceConfig(DatabaseConnectConfig):
    """数据源配置"""

    model_config = ConfigDict(from_attributes=True, extra='allow')

    schemas: Optional[Dict[str, DatabaseConnectConfig]] = Field(default=None, description='多数据库源')
    async_mode: Optional[str] = Field(default='auto', description='异步模式: auto(自动检测), sync(同步), async(异步)')


class WebApplicationConfig(BaseModel):
    """web应用配置"""

    model_config = ConfigDict(from_attributes=True, extra='allow')

    secret_key: Optional[str] = Field(default=None, description='web密钥')


class ApschedulerConfig(BaseModel):
    """调度器配置"""

    model_config = ConfigDict(from_attributes=True, extra='allow')

    enable: bool = Field(default=False, description='是否启用')
    enable_schedule_job: bool = Field(default=False, description='是否启用定时任务')
    executor_name: Optional[str] = Field(default=None, description='执行器名称')

    job_defaults: Optional[dict[str, Any]] = None
    executors: Optional[dict[str, int]] = None
    jobstores: Optional[dict[str, str]] = Field(default=None, description='任务存储')
    timezone: Optional[str] = Field(default=None, description='时区')
    logger_level: int = Field(default=logging.WARNING, description='日志级别')


class OpenapiConfig(BaseModel):
    """openapi配置"""

    model_config = ConfigDict(from_attributes=True, extra='allow')

    enable: bool = Field(default=True, description='是否启用')
    title: str = Field(default='Pyre Starlette', description='标题')
    version: str = Field(default='0.0.1', description='版本号')
    openapi_version: str = Field(default='3.0.2', description='openapi版本')
    summary: Optional[str] = Field(default=None, description='摘要')
    description: Optional[str] = Field(default=None, description='描述')
    tags: Optional[List[Union[str, dict, Tag]]] = Field(default=None, description='标签列表')
    terms_of_service: Optional[str] = Field(default=None, description='服务')
    contact: Optional[Union[dict, Contact]] = Field(default=None, description='联系')
    license: Optional[Union[dict, License]] = Field(default=None, description='许可证')
    servers: Optional[List[Union[dict, Server]]] = Field(default=None, description='服务器')
    responses: Optional[List[Union[dict, dict]]] = Field(default=None, description='响应')
    doc_url: str = Field(default='/docs', description='文档地址')
    redoc_url: Optional[str] = Field(default='/redoc', description='ReDoc地址')
    openapi_url: str = Field(default='/openapi.json', description='openapi地址')
    ui: str = Field(default="swagger", description='swagger ui')
    username: Optional[str] = Field(default=None, description='用户名')
    password: Optional[str] = Field(default=None, description='密码')


class PyreInlineConfig(BaseModel):
    """二级配置"""

    envs: Optional[str] = Field(default=None)
    env: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    additional: Optional[str] = Field(default=None)


class PyreConfig(BaseModel):
    """pyre及插件配置"""

    model_config = ConfigDict(from_attributes=True, extra='allow')

    config: PyreInlineConfig = Field(default_factory=PyreInlineConfig)
    redis: Optional[ConnectConfig] = Field(default=None, description='redis配置')
    apscheduler: Optional[ApschedulerConfig] = Field(default=None, description='apscheduler调度器配置')
    datasource: Optional[DatasourceConfig] = Field(default=None, description='数据源配置')
    application: WebApplicationConfig = Field(default_factory=WebApplicationConfig, description='web应用配置')
    openapi: Optional[OpenapiConfig] = Field(
        default_factory=OpenapiConfig, validation_alias=AliasChoices('openapi', 'swagger'), description='openapi'
    )
    locale: Optional[str] = Field(default='zh-hans', description='语言')


class LoggingFormaterConfig(BaseModel):
    """日志格式化配置"""

    console: str = Field(default=LOGGING_FORMAT)
    dateformat: Optional[str] = Field(default=None)
    file: str = Field(default=LOGGING_PLAIN_FORMAT)
    log_colors: dict[str, str] = Field(default=LOG_COLORS)


class LoggingConfig(BaseModel):
    """日志配置"""

    name: Optional[str] = Field(default=LOGGING_NAME)
    level: int = Field(default=logging.DEBUG)
    file_path: Optional[str] = Field(default=None)
    format: LoggingFormaterConfig = Field(default_factory=LoggingFormaterConfig)
    thread_log_max_entries: int = Field(default=500, description='单线程操作日志最大条数')
    thread_log_max_chars: int = Field(default=65536, description='单线程操作日志最大字符数')

    loggers: list['LoggingConfig'] = Field(default_factory=list)


class ServerConfig(BaseModel):
    """web服务配置"""

    model_config = ConfigDict(from_attributes=True, extra='allow')

    debug: Optional[bool] = Field(default=False, description='调试模式')
    host: Optional[str] = Field(default=None, description='主机')
    port: Optional[int] = Field(default=None, description='端口')


class SQLAlchemyDBConfig(BaseModel):
    """sqlalchemyDB配置"""

    datacenter_id: int = Field(default=0, description='数据中心ID')
    worker_id: int = Field(default=0, description='机器ID')
    epoch: int = Field(default=1288834974000, description='元年时间戳')


class AppConfig(BaseModel):
    """应用配置"""

    model_config = ConfigDict(from_attributes=True, extra='allow')

    server: ServerConfig = Field(default_factory=ServerConfig)
    pyre: PyreConfig = Field(default_factory=PyreConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    sqlalchemy_db: SQLAlchemyDBConfig = Field(default_factory=SQLAlchemyDBConfig)