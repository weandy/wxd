"""用户管理路由"""

import bcrypt
from flask import Blueprint, request, jsonify
from web.middleware.auth import admin_required, token_required
from web.models.database import (
    get_db, get_all_users, get_user_by_id, get_user_by_username,
    hash_password, verify_password, update_user_login, add_audit_log
)

users_bp = Blueprint('users', __name__, url_prefix='/api/users')


@users_bp.route('', methods=['GET'])
@admin_required
def list_users():
    """获取所有用户"""
    users = get_all_users()
    return jsonify({'items': users})


@users_bp.route('/<int:user_id>', methods=['GET'])
@admin_required
def get_user(user_id):
    """获取单个用户"""
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    # 不返回密码哈希
    user.pop('password_hash', None)
    return jsonify(user)


@users_bp.route('', methods=['POST'])
@admin_required
def create_user():
    """创建新用户"""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'observer')
    can_listen_recordings = data.get('can_listen_recordings', 0)
    can_transmit = data.get('can_transmit', 0)

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    # 检查用户名是否已存在
    existing = get_user_by_username(username)
    if existing:
        return jsonify({'error': '用户名已存在'}), 400

    conn = get_db()
    cursor = conn.cursor()
    password_hash = hash_password(password)

    cursor.execute("""
        INSERT INTO users (username, password_hash, role, can_listen_recordings, can_transmit)
        VALUES (?, ?, ?, ?, ?)
    """, (username, password_hash, role, can_listen_recordings, can_transmit))

    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'id': user_id}), 201


@users_bp.route('/<int:user_id>', methods=['PUT', 'POST'])
@admin_required
def update_user(user_id):
    """更新用户"""
    data = request.get_json() or {}

    conn = get_db()
    cursor = conn.cursor()

    # 检查用户是否存在
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({'error': '用户不存在'}), 404

    # 构建更新语句
    updates = []
    params = []

    if 'username' in data:
        updates.append("username = ?")
        params.append(data['username'])

    if 'password' in data and data['password']:
        updates.append("password_hash = ?")
        params.append(hash_password(data['password']))

    if 'role' in data:
        updates.append("role = ?")
        params.append(data['role'])

    if 'can_listen_recordings' in data:
        updates.append("can_listen_recordings = ?")
        params.append(1 if data['can_listen_recordings'] else 0)

    if 'can_transmit' in data:
        updates.append("can_transmit = ?")
        params.append(1 if data['can_transmit'] else 0)

    if 'avatar' in data:
        updates.append("avatar = ?")
        params.append(data['avatar'])

    if updates:
        params.append(user_id)
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

    conn.close()
    return jsonify({'success': True})


@users_bp.route('/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """删除用户"""
    if user_id == 1:
        return jsonify({'error': '不能删除管理员'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()

    if not deleted:
        return jsonify({'error': '用户不存在'}), 404

    return jsonify({'success': True})


@users_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    # 检查登录限流
    from web.models.database import check_login_rate_limit, record_login_attempt
    ip_address = request.remote_addr
    if not check_login_rate_limit(ip_address):
        return jsonify({'error': '登录尝试过多，请稍后再试'}), 429

    # 验证用户
    user = get_user_by_username(username)
    if not user or not verify_password(password, user.get('password_hash', '')):
        record_login_attempt(ip_address, username, False)
        return jsonify({'error': '用户名或密码错误'}), 401

    # 登录成功
    record_login_attempt(ip_address, username, True)
    update_user_login(user['id'])

    # 生成简单 token（生产环境应使用 JWT）
    from web.middleware.auth import generate_token
    token = generate_token(user['id'], user['username'])

    # 不返回密码
    user.pop('password_hash', None)

    return jsonify({
        'success': True,
        'token': token,
        'user': user
    })


@users_bp.route('/change-password', methods=['POST'])
@token_required
def change_password():
    """修改密码"""
    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify({'error': '密码不能为空'}), 400

    # 从 g 获取当前用户
    user_id = 1  # TODO: 从 token 获取实际用户 ID

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()

    if not row or not verify_password(old_password, row[0]):
        conn.close()
        return jsonify({'error': '原密码错误'}), 400

    # 更新密码
    new_hash = hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True})
