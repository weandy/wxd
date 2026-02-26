"""频道管理路由"""

from flask import Blueprint, request, jsonify
from web.middleware.auth import admin_required
from web.models.database import get_db

channels_bp = Blueprint('channels', __name__, url_prefix='/api/channels')


@channels_bp.route('', methods=['GET'])
def list_channels():
    """获取频道列表"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels ORDER BY channel_id")
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'items': [dict(row) for row in rows]})


@channels_bp.route('/<int:channel_id>', methods=['GET'])
def get_channel(channel_id):
    """获取单个频道"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': '频道不存在'}), 404

    return jsonify(dict(row))


@channels_bp.route('', methods=['POST'])
@admin_required
def create_channel():
    """创建频道"""
    data = request.get_json() or {}
    channel_id = data.get('channel_id')
    name = data.get('name', '')
    passcode = data.get('passcode', 0)
    auto_join = data.get('auto_join', True)

    if not channel_id:
        return jsonify({'error': '频道ID不能为空'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO channels (channel_id, name, passcode, auto_join)
            VALUES (?, ?, ?, ?)
        """, (channel_id, name, passcode, auto_join))
        conn.commit()
        channel_id = cursor.lastrowid
    except Exception as e:
        conn.close()
        return jsonify({'error': f'创建失败: {str(e)}'}), 400

    conn.close()
    return jsonify({'success': True, 'id': channel_id}), 201


@channels_bp.route('/<int:channel_id>', methods=['PUT', 'POST'])
@admin_required
def update_channel(channel_id):
    """更新频道"""
    data = request.get_json() or {}

    conn = get_db()
    cursor = conn.cursor()

    updates = []
    params = []

    if 'name' in data:
        updates.append("name = ?")
        params.append(data['name'])

    if 'passcode' in data:
        updates.append("passcode = ?")
        params.append(data['passcode'])

    if 'auto_join' in data:
        updates.append("auto_join = ?")
        params.append(1 if data['auto_join'] else 0)

    if not updates:
        return jsonify({'error': '没有要更新的内容'}), 400

    params.append(channel_id)
    cursor.execute(f"UPDATE channels SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()

    return jsonify({'success': True})


@channels_bp.route('/<int:channel_id>', methods=['DELETE'])
@admin_required
def delete_channel(channel_id):
    """删除频道"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()

    if not deleted:
        return jsonify({'error': '频道不存在'}), 404

    return jsonify({'success': True})
