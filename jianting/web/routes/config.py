"""配置管理路由"""

import os
import json
from flask import Blueprint, request, jsonify
from web.middleware.auth import admin_required
from web.models.database import get_db, add_audit_log

config_bp = Blueprint('config', __name__, url_prefix='/api/config')


@config_bp.route('', methods=['GET'])
@admin_required
def list_configs():
    """获取所有配置项"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value, category, description, updated_at FROM config ORDER BY category, key")
    rows = cursor.fetchall()
    conn.close()

    # 按分类组织
    configs = {}
    for row in rows:
        item = dict(row)
        category = item.get('category', 'other')
        if category not in configs:
            configs[category] = []
        configs[category].append(item)

    return jsonify({'configs': configs})


@config_bp.route('/<key>', methods=['GET'])
@admin_required
def get_config(key):
    """获取单个配置项"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': '配置项不存在'}), 404

    return jsonify(dict(row))


@config_bp.route('/<key>', methods=['PUT', 'POST'])
@admin_required
def update_config(key):
    """更新配置项"""
    data = request.get_json() or {}
    value = data.get('value', '')
    category = data.get('category', 'other')
    description = data.get('description', '')

    conn = get_db()
    cursor = conn.cursor()

    # 检查是否存在
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    exists = cursor.fetchone()

    from datetime import datetime
    now = datetime.now().isoformat()

    if exists:
        # 更新
        cursor.execute("""
            UPDATE config SET value = ?, category = ?, description = ?, updated_at = ?
            WHERE key = ?
        """, (value, category, description, now, key))

        # 记录历史
        cursor.execute("""
            INSERT INTO config_history (config_key, old_value, new_value, changed_by)
            VALUES (?, ?, ?, ?)
        """, (key, exists[0], value, 1))  # 简化：使用 admin ID 1
    else:
        # 插入
        cursor.execute("""
            INSERT INTO config (key, value, category, description, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (key, value, category, description, now))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'key': key})


@config_bp.route('/<key>', methods=['DELETE'])
@admin_required
def delete_config(key):
    """删除配置项"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM config WHERE key = ?", (key,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()

    if not deleted:
        return jsonify({'error': '配置项不存在'}), 404

    return jsonify({'success': True})


@config_bp.route('/history/<key>', methods=['GET'])
@admin_required
def get_config_history(key):
    """获取配置项历史"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM config_history
        WHERE config_key = ?
        ORDER BY changed_at DESC
        LIMIT 50
    """, (key,))
    rows = cursor.fetchall()
    conn.close()

    return jsonify({'items': [dict(row) for row in rows]})
