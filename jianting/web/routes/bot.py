"""Bot 状态/控制路由"""

import json
from flask import Blueprint, request, jsonify, g
from web.middleware.auth import token_required, admin_required
from web.models.database import (
    get_bot_status, send_bot_command, add_audit_log
)

bot_bp = Blueprint('bot', __name__)

# 尝试导入共享状态模块
try:
    from src.bot_state import get_bot_state
    HAS_BOT_STATE = True
except ImportError:
    HAS_BOT_STATE = False


@bot_bp.route('/status')
def status():
    """获取 Bot 状态（登录页也需要，不需要认证）"""
    # 优先从共享内存获取状态
    if HAS_BOT_STATE:
        state = get_bot_state()
        if state:
            return jsonify(state.to_dict())

    # 回退到数据库状态
    bot_status = get_bot_status()
    return jsonify({
        'running': bot_status.get('running', 'false') == 'true',
        'channel_id': bot_status.get('channel_id', ''),
        'channel_name': bot_status.get('channel_name', ''),
        'online_count': int(bot_status.get('online_count', 0)),
        'uptime': bot_status.get('uptime', ''),
        'pid': bot_status.get('pid', ''),
        'reconnect_count': int(bot_status.get('reconnect_count', 0)),
    })


@bot_bp.route('/restart', methods=['POST'])
@admin_required
def restart():
    """优雅重启 Bot"""
    cmd_id = send_bot_command('restart', created_by=g.current_user['id'])
    add_audit_log('bot_restart', g.current_user['id'],
                  g.current_user['username'], f'发送重启指令 (cmd_id={cmd_id})',
                  request.remote_addr)
    return jsonify({'success': True, 'command_id': cmd_id})


@bot_bp.route('/logs')
@token_required
def logs():
    """获取 Bot 日志（简化版：读取最近N行日志文件）"""
    import os
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
    lines_count = request.args.get('lines', 100, type=int)
    lines_count = min(lines_count, 500)  # 最多500行

    log_file = os.path.join(log_dir, 'bot.log')
    if not os.path.exists(log_file):
        return jsonify({'logs': [], 'total': 0})

    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        all_lines = f.readlines()

    recent = all_lines[-lines_count:]
    return jsonify({
        'logs': [line.rstrip() for line in recent],
        'total': len(all_lines)
    })
