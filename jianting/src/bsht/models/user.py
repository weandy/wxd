"""User related data models"""
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional
import time


class StatusCode(IntEnum):
    """状态码枚举"""
    OK = 0
    ERR_NAME_OR_PASSWORD = 1
    ERR_USER_HAVE_NO_PASSWORD = 2
    ERR_NOT_LOGIN = 3
    ERR_UNCONFIRMED = 4


@dataclass
class UserProfile:
    """用户资料"""
    user_id: int = 0
    username: str = ""
    nickname: str = ""
    email: str = ""
    photo: bytes = b''
    update_at: int = 0


@dataclass
class TokenInfo:
    """Token 信息"""
    access_token: str = ""
    access_token_expires: int = 0  # unix timestamp
    refresh_token: str = ""
    refresh_token_expires: int = 0  # unix timestamp
    
    def is_expired(self) -> bool:
        """检查 access_token 是否过期"""
        return time.time() >= self.access_token_expires
    
    def needs_refresh(self) -> bool:
        """检查是否需要刷新 token (提前5分钟)"""
        return time.time() >= (self.access_token_expires - 300)
