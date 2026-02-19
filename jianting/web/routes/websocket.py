"""WebSocket 路由 - PTT 实时音频传输"""

import json
import logging
import os
import struct
import time
from flask_socketio import emit, disconnect
from flask import request
from web import socketio
from web.middleware.auth import decode_token
from web.models.database import get_db, send_bot_command, get_user_by_id

logger = logging.getLogger("BotWS")

# 尝试导入 Bot 状态模块
try:
    from src.bot_state import get_bot_state
    HAS_BOT_STATE = True
except ImportError:
    HAS_BOT_STATE = False
    def get_bot_state():
        return None


def broadcast_bot_status():
    """广播 Bot 状态给所有客户端"""
    if not HAS_BOT_STATE:
        return
    state = get_bot_state()
    if state:
        socketio.emit('bot:status', state.to_dict(), broadcast=True)


def broadcast_channel_update(channel_id: int, channel_name: str, online_count: int):
    """广播频道更新"""
    socketio.emit('bot:channel', {
        'channel_id': channel_id,
        'channel_name': channel_name,
        'online_count': online_count
    }, broadcast=True)


def broadcast_speaking(user_id: str, user_name: str, speaking: bool):
    """广播说话状态"""
    socketio.emit('bot:speaking', {
        'user_id': user_id,
        'user_name': user_name,
        'speaking': speaking
    }, broadcast=True)


def broadcast_recording(recording: dict):
    """广播新录音"""
    socketio.emit('bot:recording', recording, broadcast=True)


# 已认证的 WebSocket 会话
authenticated_sessions = {}

# ========== Bot 连接管理 ==========
bot_connections = {}  # sid -> bot_info


@socketio.on('connect', namespace='/bot')
def handle_bot_connect():
    """Bot WebSocket 连接 (无需认证)"""
    logger.info(f"[Bot WS] 新连接: {request.sid}")
    bot_connections[request.sid] = {
        'connected_at': time.time(),
        'bot_name': 'BSHT Bot'
    }
    emit('bot:connected', {'sid': request.sid})


@socketio.on('disconnect', namespace='/bot')
def handle_bot_disconnect():
    """Bot WebSocket 断开"""
    logger.info(f"[Bot WS] 断开: {request.sid}")
    bot_connections.pop(request.sid, None)


@socketio.on('bot:auth', namespace='/bot')
def handle_bot_auth(data):
    """Bot 认证"""
    logger.info(f"[Bot WS] Bot 认证: {data}")
    if request.sid in bot_connections:
        bot_connections[request.sid].update(data)
        bot_connections[request.sid]['authenticated'] = True
    emit('bot:auth_ok')


@socketio.on('bot:status', namespace='/bot')
def handle_bot_status(data):
    """接收 Bot 状态，推送给前端"""
    # 推送给所有连接的浏览器客户端
    emit('bot:status', data, broadcast=True)
    logger.debug(f"[Bot WS] 转发状态: {data}")


@socketio.on('bot:channel', namespace='/bot')
def handle_bot_channel(data):
    """接收频道状态，推送给前端"""
    emit('bot:channel', data, broadcast=True)
    logger.info(f"[Bot WS] 转发频道: {data.get('channel_name')}")


@socketio.on('bot:recording', namespace='/bot')
def handle_bot_recording(data):
    """接收新录音，推送给前端"""
    emit('bot:recording', data, broadcast=True)
    logger.info(f"[Bot WS] 转发录音: {data.get('filename')}")


@socketio.on('bot:speaking', namespace='/bot')
def handle_bot_speaking(data):
    """接收说话状态，推送给前端"""
    emit('bot:speaking', data, broadcast=True)


def get_bot_connected() -> bool:
    """检查 Bot 是否连接"""
    return len(bot_connections) > 0


@socketio.on('connect')
def handle_connect():
    """WebSocket 连接 - 验证 token"""
    token = request.args.get('token', '')
    payload = decode_token(token)
    if not payload:
        disconnect()
        return

    user = get_user_by_id(payload['user_id'])
    if not user:
        disconnect()
        return

    authenticated_sessions[request.sid] = {
        'user_id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'can_transmit': bool(user['can_transmit'])
    }
    emit('auth_ok', {'username': user['username']})


@socketio.on('disconnect')
def handle_disconnect():
    """WebSocket 断开"""
    authenticated_sessions.pop(request.sid, None)


@socketio.on('ptt:start')
def handle_ptt_start(data):
    """开始 PTT 发射"""
    session = authenticated_sessions.get(request.sid)
    if not session:
        emit('error', {'message': '未认证'})
        return

    if not session['can_transmit'] and session['role'] != 'admin':
        emit('error', {'message': '无发射权限'})
        return

    channel_id = data.get('channel_id')
    if not channel_id:
        emit('error', {'message': '未指定频道'})
        return

    # 通知 Bot 进程准备接收音频
    cmd_id = send_bot_command(
        'ptt_start',
        json.dumps({'channel_id': channel_id, 'user': session['username']}),
        session['user_id']
    )
    emit('ptt:ready', {'command_id': cmd_id, 'channel_id': channel_id})


@socketio.on('ptt:audio')
def handle_ptt_audio(data):
    """接收 PTT 音频帧 (binary), 写入共享缓冲目录"""
    session = authenticated_sessions.get(request.sid)
    if not session:
        return

    # data 是二进制音频帧: [seq:uint16][timestamp:uint32][pcm_data:bytes]
    if isinstance(data, bytes) and len(data) > 6:
        seq = struct.unpack('<H', data[:2])[0]
        pcm_data = data[6:]

        # 写入共享缓冲目录, Bot 进程轮询读取
        ptt_dir = os.path.join('data', 'ptt_buffer')
        os.makedirs(ptt_dir, exist_ok=True)
        fname = f"{seq:06d}.pcm"
        filepath = os.path.join(ptt_dir, fname)
        with open(filepath, 'wb') as f:
            f.write(pcm_data)


@socketio.on('ptt:stop')
def handle_ptt_stop():
    """停止 PTT 发射"""
    session = authenticated_sessions.get(request.sid)
    if not session:
        return

    send_bot_command(
        'ptt_stop',
        json.dumps({'user': session['username']}),
        session['user_id']
    )
    emit('ptt:stopped')


@socketio.on('ptt:play_audio')
def handle_play_audio(data):
    """发射音频库文件"""
    session = authenticated_sessions.get(request.sid)
    if not session:
        emit('error', {'message': '未认证'})
        return

    if not session['can_transmit'] and session['role'] != 'admin':
        emit('error', {'message': '无发射权限'})
        return

    audio_id = data.get('audio_id')
    channel_id = data.get('channel_id')

    if not audio_id or not channel_id:
        emit('error', {'message': '参数不完整'})
        return

    cmd_id = send_bot_command(
        'play_audio',
        json.dumps({
            'audio_id': audio_id,
            'channel_id': channel_id,
            'user': session['username']
        }),
        session['user_id']
    )
    emit('ptt:playing', {'command_id': cmd_id})
