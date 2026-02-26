"""定时任务管理路由"""

import json
from datetime import datetime
from flask import Blueprint, request, jsonify
from web.middleware.auth import admin_required
from web.models.database import get_db

scheduled_tasks_bp = Blueprint('scheduled_tasks', __name__, url_prefix='/api/scheduled-tasks')


@scheduled_tasks_bp.route('', methods=['GET'])
@admin_required
def list_tasks():
    """获取定时任务列表"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT st.*, al.name as audio_name
        FROM scheduled_tasks st
        LEFT JOIN audio_library al ON st.audio_id = al.id
        ORDER BY st.id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'items': [dict(row) for row in rows]})


@scheduled_tasks_bp.route('/<int:task_id>', methods=['GET'])
@admin_required
def get_task(task_id):
    """获取单个任务"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': '任务不存在'}), 404

    return jsonify(dict(row))


@scheduled_tasks_bp.route('', methods=['POST'])
@admin_required
def create_task():
    """创建定时任务"""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    audio_id = data.get('audio_id')
    channel_id = data.get('channel_id')
    trigger_type = data.get('trigger_type', 'fixed')
    schedule_config = data.get('schedule_config', {})
    time_window_start = data.get('time_window_start')
    time_window_end = data.get('time_window_end')
    enabled = data.get('enabled', True)

    if not name or not audio_id or not channel_id:
        return jsonify({'error': '名称、音频ID、频道ID不能为空'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO scheduled_tasks (name, audio_id, channel_id, trigger_type, schedule_config, time_window_start, time_window_end, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, audio_id, channel_id, trigger_type, json.dumps(schedule_config), time_window_start, time_window_end, enabled))
        conn.commit()
        task_id = cursor.lastrowid
    except Exception as e:
        conn.close()
        return jsonify({'error': f'创建失败: {str(e)}'}), 400

    conn.close()
    return jsonify({'success': True, 'id': task_id}), 201


@scheduled_tasks_bp.route('/<int:task_id>', methods=['PUT', 'POST'])
@admin_required
def update_task(task_id):
    """更新定时任务"""
    data = request.get_json() or {}

    conn = get_db()
    cursor = conn.cursor()

    updates = []
    params = []

    if 'name' in data:
        updates.append("name = ?")
        params.append(data['name'])

    if 'audio_id' in data:
        updates.append("audio_id = ?")
        params.append(data['audio_id'])

    if 'channel_id' in data:
        updates.append("channel_id = ?")
        params.append(data['channel_id'])

    if 'trigger_type' in data:
        updates.append("trigger_type = ?")
        params.append(data['trigger_type'])

    if 'schedule_config' in data:
        updates.append("schedule_config = ?")
        params.append(json.dumps(data['schedule_config']))

    if 'time_window_start' in data:
        updates.append("time_window_start = ?")
        params.append(data['time_window_start'])

    if 'time_window_end' in data:
        updates.append("time_window_end = ?")
        params.append(data['time_window_end'])

    if 'enabled' in data:
        updates.append("enabled = ?")
        params.append(1 if data['enabled'] else 0)

    if not updates:
        return jsonify({'error': '没有要更新的内容'}), 400

    params.append(task_id)
    cursor.execute(f"UPDATE scheduled_tasks SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()

    return jsonify({'success': True})


@scheduled_tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@admin_required
def delete_task(task_id):
    """删除定时任务"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()

    if not deleted:
        return jsonify({'error': '任务不存在'}), 404

    return jsonify({'success': True})


@scheduled_tasks_bp.route('/<int:task_id>/toggle', methods=['POST'])
@admin_required
def toggle_task(task_id):
    """启用/禁用任务"""
    data = request.get_json() or {}
    enabled = data.get('enabled', True)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE scheduled_tasks SET enabled = ? WHERE id = ?", (1 if enabled else 0, task_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True})


@scheduled_tasks_bp.route('/<int:task_id>/run', methods=['POST'])
@admin_required
def run_task(task_id):
    """手动执行任务"""
    # TODO: 实现手动执行逻辑
    return jsonify({'message': '手动执行功能待实现'})


@scheduled_tasks_bp.route('/<int:task_id>/logs', methods=['GET'])
@admin_required
def get_task_logs(task_id):
    """获取任务执行日志"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM scheduled_task_logs
        WHERE task_id = ?
        ORDER BY executed_at DESC
        LIMIT 50
    """, (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'items': [dict(row) for row in rows]})
