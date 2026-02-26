"""数据维护路由"""

import os
import sqlite3
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from web.middleware.auth import admin_required
from web.models.database import get_db

data_maintenance_bp = Blueprint('data_maintenance', __name__, url_prefix='/api/data-maintenance')


@data_maintenance_bp.route('/stats', methods=['GET'])
@admin_required
def get_stats():
    """获取数据统计"""
    db_path = get_db()
    conn = get_db(db_path)
    cursor = conn.cursor()

    stats = {}

    # 录音记录数
    cursor.execute("SELECT COUNT(*) FROM recordings")
    stats['recordings_count'] = cursor.fetchone()[0]

    # 音频库数量
    cursor.execute("SELECT COUNT(*) FROM audio_library")
    stats['audio_library_count'] = cursor.fetchone()[0]

    # 用户数量
    cursor.execute("SELECT COUNT(*) FROM users")
    stats['users_count'] = cursor.fetchone()[0]

    # 定时任务数量
    cursor.execute("SELECT COUNT(*) FROM scheduled_tasks")
    stats['scheduled_tasks_count'] = cursor.fetchone()[0]

    # 录音文件总大小
    cursor.execute("SELECT SUM(file_size) FROM audio_library")
    total_size = cursor.fetchone()[0] or 0
    stats['audio_library_size_mb'] = round(total_size / 1024 / 1024, 2)

    # 今日新增录音
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM recordings WHERE timestamp LIKE ?", (f"{today}%",))
    stats['today_recordings'] = cursor.fetchone()[0]

    conn.close()
    return jsonify(stats)


@data_maintenance_bp.route('/cleanup/recordings', methods=['POST'])
@admin_required
def cleanup_recordings():
    """清理录音记录"""
    data = request.get_json() or {}
    days = data.get('days', 30)  # 保留天数
    delete_files = data.get('delete_files', False)  # 是否删除文件

    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    conn = get_db()
    cursor = conn.cursor()

    # 获取要删除的录音
    cursor.execute("SELECT id, filepath FROM recordings WHERE timestamp < ?", (cutoff_date,))
    recordings = cursor.fetchall()

    deleted_count = 0
    deleted_files = 0

    for row in recordings:
        # 删除文件
        if delete_files and row[1] and os.path.exists(row[1]):
            try:
                os.remove(row[1])
                deleted_files += 1
            except Exception:
                pass

        # 删除记录
        cursor.execute("DELETE FROM recordings WHERE id = ?", (row[0],))
        deleted_count += 1

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'deleted_count': deleted_count,
        'deleted_files': deleted_files
    })


@data_maintenance_bp.route('/cleanup/audio-library', methods=['POST'])
@admin_required
def cleanup_audio_library():
    """清理未使用的音频"""
    data = request.get_json() or {}
    unused_only = data.get('unused_only', True)

    conn = get_db()
    cursor = conn.cursor()

    if unused_only:
        # 删除使用次数为 0 的音频
        cursor.execute("SELECT id, filepath FROM audio_library WHERE use_count = 0")
    else:
        # 删除所有（危险）
        cursor.execute("SELECT id, filepath FROM audio_library")

    audios = cursor.fetchall()

    deleted_count = 0
    deleted_files = 0

    for row in audios:
        # 删除文件
        if row[1] and os.path.exists(row[1]):
            try:
                os.remove(row[1])
                deleted_files += 1
            except Exception:
                pass

        # 删除记录
        cursor.execute("DELETE FROM audio_library WHERE id = ?", (row[0],))
        deleted_count += 1

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'deleted_count': deleted_count,
        'deleted_files': deleted_files
    })


@data_maintenance_bp.route('/optimize', methods=['POST'])
@admin_required
def optimize():
    """数据库优化"""
    db_path = get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # VACUUM
    cursor.execute("VACUUM")

    # ANALYZE
    cursor.execute("ANALYZE")

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': '数据库优化完成'})


@data_maintenance_bp.route('/repair', methods=['POST'])
@admin_required
def repair():
    """数据库修复"""
    db_path = get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查并修复
    cursor.execute("PRAGMA integrity_check")

    result = cursor.fetchone()

    conn.close()

    return jsonify({'success': result[0] == 'ok', 'result': result[0]})
