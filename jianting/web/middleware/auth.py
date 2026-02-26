"""认证中间件"""
from functools import wraps
from flask import request, jsonify, g
import os
import time

# 简单的 API Token 验证
API_TOKEN = os.getenv('API_TOKEN', 'dev-token-change-in-production')

# 简单的 token 存储（生产环境应使用 Redis 或数据库）
_active_tokens = {}


def generate_token(user_id: int, user_name: str = None) -> str:
    """生成简单的 token"""
    import secrets
    token = secrets.token_urlsafe(32)
    _active_tokens[token] = {
        'user_id': user_id,
        'user_name': user_name,
        'created_at': time.time()
    }
    return token


def decode_token(token: str) -> dict:
    """解码 token"""
    if not token:
        return None

    # 简单实现：直接检查 token
    if token in _active_tokens:
        return _active_tokens[token]

    # 兼容：也支持简单的 user_id 格式
    if token.isdigit():
        return {'user_id': int(token), 'user_name': 'user'}

    return None


def get_user_by_id(user_id: int) -> dict:
    """根据用户 ID 获取用户信息"""
    # 简单实现：返回默认用户
    # 实际应该从数据库查询
    if user_id == 1:
        return {'id': 1, 'username': 'admin', 'role': 'admin'}
    return {'id': user_id, 'username': f'user{user_id}', 'role': 'user'}


def token_required(f):
    """API Token 验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查 URL 参数或 Header 中的 token
        token = request.args.get('token') or request.headers.get('X-API-Token')

        if not token:
            return jsonify({'error': '缺少认证令牌'}), 401

        if token != API_TOKEN:
            return jsonify({'error': '无效的认证令牌'}), 401

        # 设置当前用户
        g.current_user = {'token': token}
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """管理员权限验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查是否为管理员
        # 可以从 session、token 或其他方式获取
        is_admin = request.args.get('admin') == 'true' or request.headers.get('X-Admin') == 'true'

        if not is_admin:
            # 简单实现：允许所有通过 token 验证的请求
            # 实际项目中应该检查用户角色
            pass

        return f(*args, **kwargs)

    return decorated_function


def can_listen_recordings_required(f):
    """收听录音权限验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 简单实现：允许所有请求
        # 实际项目中应该检查用户权限
        return f(*args, **kwargs)

    return decorated_function


def can_transmit_required(f):
    """发射权限验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 简单实现：允许所有请求
        # 实际项目中应该检查用户权限
        return f(*args, **kwargs)

    return decorated_function
