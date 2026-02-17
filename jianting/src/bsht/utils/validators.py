"""Validation utilities"""
from typing import Any, Optional
import re


def validate_user_id(user_id: Any) -> bool:
    """验证用户ID"""
    try:
        uid = int(user_id)
        return uid > 0
    except (ValueError, TypeError):
        return False


def validate_channel_id(channel_id: Any) -> bool:
    """验证频道ID"""
    try:
        cid = int(channel_id)
        return cid > 0
    except (ValueError, TypeError):
        return False


def validate_token(token: str) -> bool:
    """验证Token格式"""
    if not token or not isinstance(token, str):
        return False
    return len(token) > 10


def validate_nickname(nickname: str) -> bool:
    """验证昵称"""
    if not nickname or not isinstance(nickname, str):
        return False
    return 1 <= len(nickname) <= 50


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除非法字符"""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)
