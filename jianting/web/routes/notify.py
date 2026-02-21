"""通知推送管理路由"""

import json
from flask import Blueprint, request, jsonify, g
from web.middleware.auth import admin_required, token_required
from web.models.database import get_db, add_audit_log

notify_bp = Blueprint('notify', __name__)


# ========== 推送服务 CRUD ==========

@notify_bp.route('/services')
@admin_required
def list_services():
    """获取推送服务列表"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, type, url, token, config, enabled, created_at, updated_at FROM notify_services ORDER BY created_at")
    services = [dict(row) for row in cursor.fetchall()]

    # 每个服务附带用户数
    for svc in services:
        cursor.execute(
            "SELECT COUNT(*) FROM notify_users WHERE service_id = ?",
            (svc['id'],)
        )
        svc['user_count'] = cursor.fetchone()[0]
        # 脱敏 config 和 token
        if svc.get('config'):
            try:
                cfg = json.loads(svc['config'])
                for k in cfg:
                    v = str(cfg[k])
                    if len(v) > 8:
                        cfg[k] = v[:4] + '****' + v[-4:]
                svc['config_masked'] = cfg
            except Exception:
                svc['config_masked'] = {}
        # 脱敏 token
        if svc.get('token') and len(svc['token']) > 8:
            svc['token_masked'] = svc['token'][:4] + '****' + svc['token'][-4:]
        else:
            svc['token_masked'] = svc.get('token', '')

    conn.close()
    return jsonify({'items': services})


@notify_bp.route('/services', methods=['POST'])
@admin_required
def create_service():
    """创建推送服务"""
    data = request.get_json()
    name = data.get('name', '').strip()
    svc_type = data.get('type', '').strip()
    config = data.get('config', {})
    url = data.get('url', '').strip()
    token = data.get('token', '').strip()

    if not name or not svc_type:
        return jsonify({'error': '名称和类型不能为空'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notify_services (name, type, url, token, config, enabled)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (name, svc_type, url, token, json.dumps(config)))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    add_audit_log('create_notify_service', g.current_user['id'],
                  g.current_user['username'],
                  f'创建推送服务 {name} ({svc_type})',
                  request.remote_addr)

    # 如果是 WxPusher 服务，触发热更新
    if svc_type == 'wxpusher':
        try:
            from src.wx_pusher import reload_pusher
            reload_pusher()
        except Exception:
            pass

    return jsonify({'success': True, 'id': new_id}), 201


@notify_bp.route('/services/<int:svc_id>', methods=['PUT'])
@admin_required
def update_service(svc_id):
    """更新推送服务"""
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, type FROM notify_services WHERE id = ?", (svc_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '服务不存在'}), 404

    svc_type = row[1]

    updates = []
    params = []
    for field in ['name', 'type']:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])

    if 'config' in data:
        updates.append("config = ?")
        params.append(json.dumps(data['config']))

    if 'url' in data:
        updates.append("url = ?")
        params.append(data['url'])

    if 'token' in data:
        updates.append("token = ?")
        params.append(data['token'])

    if 'enabled' in data:
        updates.append("enabled = ?")
        params.append(1 if data['enabled'] else 0)

    if updates:
        from datetime import datetime
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(svc_id)
        cursor.execute(
            f"UPDATE notify_services SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()

    conn.close()

    # 如果是 WxPusher 服务，触发热更新
    if svc_type == 'wxpusher':
        try:
            from src.wx_pusher import reload_pusher
            reload_pusher()
        except Exception:
            pass

    return jsonify({'success': True})


@notify_bp.route('/services/<int:svc_id>', methods=['DELETE'])
@admin_required
def delete_service(svc_id):
    """删除推送服务 (连同其用户)"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM notify_services WHERE id = ?", (svc_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '服务不存在'}), 404

    cursor.execute("DELETE FROM notify_users WHERE service_id = ?", (svc_id,))
    cursor.execute("DELETE FROM notify_services WHERE id = ?", (svc_id,))
    conn.commit()
    conn.close()

    add_audit_log('delete_notify_service', g.current_user['id'],
                  g.current_user['username'],
                  f'删除推送服务 {row["name"]}',
                  request.remote_addr)

    return jsonify({'success': True})


# ========== 推送用户 CRUD ==========

@notify_bp.route('/services/<int:svc_id>/users')
@admin_required
def list_users(svc_id):
    """获取推送服务的用户列表"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM notify_users WHERE service_id = ? ORDER BY created_at",
        (svc_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'items': [dict(row) for row in rows]})


@notify_bp.route('/services/<int:svc_id>/users', methods=['POST'])
@admin_required
def add_user(svc_id):
    """添加推送用户"""
    data = request.get_json()
    name = data.get('name', '').strip()
    identifier = data.get('user_identifier', '').strip()
    keywords = data.get('keywords', '*').strip()

    if not name or not identifier:
        return jsonify({'error': '用户名和标识不能为空'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notify_users (service_id, name, user_identifier, keywords, enabled)
        VALUES (?, ?, ?, ?, 1)
    """, (svc_id, name, identifier, keywords))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'id': new_id}), 201


@notify_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """更新推送用户"""
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()

    updates = []
    params = []
    for field in ['name', 'user_identifier', 'keywords']:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    if 'enabled' in data:
        updates.append("enabled = ?")
        params.append(1 if data['enabled'] else 0)

    if updates:
        params.append(user_id)
        cursor.execute(
            f"UPDATE notify_users SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()

    conn.close()
    return jsonify({'success': True})


@notify_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """删除推送用户"""
    # 先获取服务类型
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.type FROM notify_users u
        JOIN notify_services s ON u.service_id = s.id
        WHERE u.id = ?
    """, (user_id,))
    row = cursor.fetchone()
    svc_type = row[0] if row else None

    conn.execute("DELETE FROM notify_users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    # 如果是 WxPusher 服务，触发热更新
    if svc_type == 'wxpusher':
        try:
            from src.wx_pusher import reload_pusher
            reload_pusher()
        except Exception:
            pass

    return jsonify({'success': True})


# ========== 热更新端点 ==========

@notify_bp.route('/reload', methods=['POST'])
@admin_required
def reload_pusher_service():
    """热更新推送配置（从数据库重新加载）"""
    try:
        from src.wx_pusher import reload_pusher
        pusher = reload_pusher()
        if pusher:
            return jsonify({'success': True, 'message': f'热更新成功: {len(pusher.targets)} 个目标'})
        else:
            return jsonify({'success': False, 'message': '热更新失败：无有效配置'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'热更新失败: {str(e)}'}), 500


@notify_bp.route('/test', methods=['POST'])
@admin_required
def test_pusher():
    """测试推送功能"""
    data = request.get_json()
    user_id = data.get('user_id')  # 可选，指定用户

    try:
        from src.wx_pusher import get_pusher
        pusher = get_pusher()

        if not pusher:
            return jsonify({'success': False, 'message': '推送器未初始化'}), 400

        # 发送测试消息
        success = pusher.send(
            title="测试消息",
            content="这是一条测试消息，用于验证推送配置是否正确。",
            userid=user_id
        )

        if success:
            return jsonify({'success': True, 'message': '测试消息发送成功'})
        else:
            return jsonify({'success': False, 'message': '测试消息发送失败'}), 400

    except Exception as e:
        return jsonify({'success': False, 'message': f'测试失败: {str(e)}'}), 500
