"""
认证服务 - 用户认证和会话管理
"""
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import secrets


class AuthService:
    """认证服务"""

    # Token 存储（生产环境应使用 Redis）
    _tokens: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def hash_password(password: str) -> str:
        """哈希密码"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """验证密码"""
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

    @staticmethod
    def authenticate_user(db, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        验证用户凭据

        Args:
            db: 数据库实例
            username: 用户名
            password: 密码

        Returns:
            用户信息字典，验证失败返回 None
        """
        user = db.get_user_by_username(username)

        if not user:
            return None

        if not user.is_active:
            return None

        if not AuthService.verify_password(password, user.password_hash):
            return None

        # 更新最后登录时间
        db.update_user_login(user.id)

        return {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "role": user.role
        }

    @staticmethod
    def create_session(user_info: Dict[str, Any]) -> str:
        """
        创建会话

        Args:
            user_info: 用户信息

        Returns:
            Session Token
        """
        token = secrets.token_urlsafe(32)

        # 存储会话信息
        AuthService._tokens[token] = {
            "user": user_info,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(hours=24)
        }

        return token

    @staticmethod
    def get_session(token: str) -> Optional[Dict[str, Any]]:
        """
        获取会话

        Args:
            token: Session Token

        Returns:
            会话信息，不存在或过期返回 None
        """
        session = AuthService._tokens.get(token)

        if not session:
            return None

        # 检查是否过期
        if datetime.now() > session["expires_at"]:
            del AuthService._tokens[token]
            return None

        return session

    @staticmethod
    def delete_session(token: str):
        """删除会话"""
        if token in AuthService._tokens:
            del AuthService._tokens[token]

    @staticmethod
    def cleanup_expired_sessions():
        """清理过期会话"""
        now = datetime.now()
        expired_tokens = [
            token for token, session in AuthService._tokens.items()
            if now > session["expires_at"]
        ]

        for token in expired_tokens:
            del AuthService._tokens[token]

        return len(expired_tokens)


# 全局认证服务实例
auth_service = AuthService()
