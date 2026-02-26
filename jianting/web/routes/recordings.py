"""录音管理路由"""

import os
from flask import Blueprint, request, jsonify, send_file
from web.middleware.auth import can_listen_recordings_required
from web.models.database import get_db, get_recordings, get_recording_by_id, delete_recording, add_audit_log

recordings_bp = Blueprint('recordings', __name__, url_prefix='/api/recordings')


@recordings_bp.route('', methods=['GET'])
@can_listen_recordings_required
def list_recordings():
    """获取录音列表（分页+过滤）"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    channel_id = request.args.get('channel_id', type=int)
    user_name = request.args.get('user_name')
    keyword = request.args.get('keyword')

    result = get_recordings(
        page=page,
        per_page=per_page,
        channel_id=channel_id,
        user_name=user_name,
        keyword=keyword
    )

    return jsonify(result)


@recordings_bp.route('/<int:recording_id>', methods=['GET'])
@can_listen_recordings_required
def get_recording(recording_id):
    """获取单条录音详情"""
    recording = get_recording_by_id(recording_id)

    if not recording:
        return jsonify({'error': '录音不存在'}), 404

    return jsonify(recording)


@recordings_bp.route('/<int:recording_id>/file', methods=['GET'])
@can_listen_recordings_required
def download_recording(recording_id):
    """下载录音文件"""
    recording = get_recording_by_id(recording_id)

    if not recording:
        return jsonify({'error': '录音不存在'}), 404

    filepath = recording.get('filepath')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404

    filename = recording.get('filename', os.path.basename(filepath))
    return send_file(filepath, as_attachment=True, download_name=filename)


@recordings_bp.route('/<int:recording_id>', methods=['DELETE'])
@can_listen_recordings_required
def remove_recording(recording_id):
    """删除录音"""
    # TODO: 添加权限检查
    deleted = delete_recording(recording_id)

    if not deleted:
        return jsonify({'error': '录音不存在'}), 404

    return jsonify({'success': True})


@recordings_bp.route('/stats/today', methods=['GET'])
@can_listen_recordings_required
def today_stats():
    """获取今日统计"""
    from web.models.database import get_today_stats
    stats = get_today_stats()
    return jsonify(stats)


@recordings_bp.route('/scan', methods=['POST'])
@can_listen_recordings_required
def scan_recordings():
    """手动扫描录音目录"""
    # TODO: 实现扫描功能
    return jsonify({'message': '扫描功能待实现'})
