import random

from authlib.jose import JoseError, jwt

from pyre_starlette import models
from werkzeug.security import check_password_hash, generate_password_hash

from .enums import UserGender
from ...constants import GeneralStatus
from ...exceptions import UnauthorizedException


class AbstractUser(models.Model):
    """抽象基础用户"""
    __abstract__ = True

    # 默认一周过期
    __token_duration__ = 604800

    # jwt算法
    __jwt_header__ = {'alg': 'HS256'}

    def generate_user_token(
        self,
        **kwargs
    ) -> str:
        """
        生成用户token
        :return: 加密过的token
        """
        header = kwargs.get('header', self.__jwt_header__)
        payload = kwargs.get('payload', {})
        key = kwargs.get('key')
        return jwt.encode(header=header, payload=payload, key=key).decode('utf-8')

    @classmethod
    def verify_user_token(
        cls,
        token: str,
        **kwargs
    ):
        """
        验证token
        :return: 解密后的payload
        """
        if not token:
            raise UnauthorizedException
        key = kwargs.get('key')
        # 解密token
        try:
            payload = jwt.decode(token, key)
        except JoseError:
            raise UnauthorizedException
        return payload


class AbstractPasswordUser(AbstractUser):
    """抽象密码用户"""
    __abstract__ = True
    password_hash_method: str = 'pbkdf2:sha256'

    password_hash = models.StringField(255, nullable=True, comment='密码')

    def set_password(self, password: str) -> None:
        """设置用户密码，保存为 Hash 值"""
        self.password_hash = generate_password_hash(password, method=self.password_hash_method)

    def check_password(self, password: str) -> bool:
        """验证密码"""
        return check_password_hash(self.password_hash, password)


class AbstractUserProfile(models.Model):
    """抽象用户资料"""
    __abstract__ = True

    """默认头像"""
    default_avatar = "static/img/default_avatar.png"

    nickname = models.StringField(64, nullable=False, comment="昵称")
    full_name = models.StringField(32, nullable=True, comment="姓名")
    avatar = models.StringField(255, nullable=True, default=default_avatar, comment="头像")
    wechat_num = models.StringField(32, comment='微信号')
    gender = models.IntEnumField(UserGender, nullable=False, default=UserGender.UNKNOWN, comment="性别")
    birthday = models.DateField(nullable=True, comment="生日")
    location = models.StringField(128, nullable=True, comment="地区")
    signature = models.StringField(255, nullable=True, comment="个性签名")

    @classmethod
    def get_default_nickname(cls):
        return f"用户{random.randint(1000, 9999)}"


class BaseUser(AbstractPasswordUser, AbstractUserProfile):
    """基础用户"""
    __abstract__ = True

    # 启用软删除
    default_soft_delete = True

    username = models.StringField(16, nullable=True, comment="用户名")
    email = models.StringField(32, nullable=True, comment="邮箱")
    phone = models.StringField(16, nullable=True, comment="手机号")
    last_login_time = models.BigIntegerField(comment='上次登录时间')
    login_ip = models.StringField(128, comment='登录IP')
    status = models.IntEnumField(
        GeneralStatus,
        nullable=False,
        default=GeneralStatus.NORMAL,
        server_default=str(GeneralStatus.NORMAL.value),
        comment="状态"
    )