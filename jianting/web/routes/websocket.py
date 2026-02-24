"""WebSocket 路由 - PTT 实时音频传输"""

import json
import logging
import time
from flask_socketio import emit, disconnect
from flask import request
from web import socketio
from web.middleware.auth import decode_token
from web.models.database import get_db, send_bot_command, get_user_by_id

# 使用项目统一日志（确保有 handler）
try:
    from src.logging_setup import get_logger
    logger = get_logger("BotWS", "main")
except ImportError:
    logger = logging.getLogger("BotWS")
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(logging.INFO)

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
        socketio.emit('bot:status', state.to_dict())


def broadcast_channel_update(channel_id: int, channel_name: str, online_count: int):
    """广播频道更新到默认 namespace (浏览器客户端)"""
    socketio.emit('bot:channel', {
        'channel_id': channel_id,
        'channel_name': channel_name,
        'online_count': online_count
    })


def broadcast_speaking(user_id: str, user_name: str, speaking: bool):
    """广播说话状态"""
    socketio.emit('bot:speaking', {
        'user_id': user_id,
        'user_name': user_name,
        'speaking': speaking
    })


def broadcast_recording(recording: dict):
    """广播新录音"""
    try:
        socketio.emit('bot:recording', recording)
        logger.info(f"[WS] 广播新录音: {recording.get('user_name', '?')} {recording.get('duration', 0):.1f}s")
    except Exception as e:
        logger.error(f"[WS] 广播录音失败: {e}")


# 已认证的 WebSocket 会话
authenticated_sessions = {}

# PTT 发射状态: sid -> True (已通过 ptt:start 验证且正在发射)
_ptt_active_sessions = {}

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
    """接收 Bot 状态，转发给浏览器客户端 (namespace='/')"""
    socketio.emit('bot:status', data, namespace='/')
    logger.debug(f"[Bot WS] 转发状态: {data}")


@socketio.on('bot:channel', namespace='/bot')
def handle_bot_channel(data):
    """接收频道状态，转发给浏览器客户端 (namespace='/')"""
    socketio.emit('bot:channel', data, namespace='/')
    logger.info(f"[Bot WS] 转发频道: {data.get('channel_name')}")


@socketio.on('bot:recording', namespace='/bot')
def handle_bot_recording(data):
    """接收新录音，转发给浏览器客户端 (namespace='/')"""
    socketio.emit('bot:recording', data, namespace='/')
    logger.info(f"[Bot WS] 转发录音: {data.get('filename')}")


@socketio.on('bot:speaking', namespace='/bot')
def handle_bot_speaking(data):
    """接收说话状态，转发给浏览器客户端 (namespace='/')"""
    socketio.emit('bot:speaking', data, namespace='/')


def get_bot_connected() -> bool:
    """检查 Bot 是否连接"""
    return len(bot_connections) > 0


# ========== 浏览器客户端连接管理 ==========

@socketio.on('connect')
def handle_connect():
    """WebSocket 连接 - 验证 token，维护监听计数"""
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

    # 维护 listener 计数 (供 transmitter.py 判断是否需要广播)
    import web.routes.transmitter as _tx
    _tx._listener_count += 1
    logger.info(f"[WS] 客户端连接: {user['username']} (listeners={_tx._listener_count})")

    emit('auth_ok', {'username': user['username']})


@socketio.on('disconnect')
def handle_disconnect():
    """WebSocket 断开 - 清理会话，减少监听计数"""
    session = authenticated_sessions.pop(request.sid, None)
    _ptt_active_sessions.pop(request.sid, None)

    import web.routes.transmitter as _tx
    _tx._listener_count = max(0, _tx._listener_count - 1)

    username = session['username'] if session else 'unknown'
    logger.info(f"[WS] 客户端断开: {username} (listeners={_tx._listener_count})")


# ========== PTT ==========

@socketio.on('ptt:start')
def handle_ptt_start(data):
    """开始 PTT 发射 — 直接调用 Bot listener"""
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

    # 通过 bot_bridge 直接调用 listener
    from web.bot_bridge import get_bot_listener
    listener = get_bot_listener()
    if not listener:
        emit('error', {'message': 'Bot 未连接'})
        return

    success = listener.start_transmit_web()
    if not success:
        emit('error', {'message': '发射启动失败'})
        return

    # 标记此 session 进入 PTT 发射状态
    _ptt_active_sessions[request.sid] = True
    emit('ptt:ready', {'channel_id': channel_id})
    logger.info(f"[WS] PTT 开始: {session['username']} -> 频道 {channel_id}")


@socketio.on('ptt:audio')
def handle_ptt_audio(data):
    """接收 PTT 音频帧 (裸 PCM), 直接喂给 Bot listener Opus 编码 + RTP 发射"""
    session = authenticated_sessions.get(request.sid)
    if not session:
        return

    # 权限校验 + PTT 状态守卫
    if not _ptt_active_sessions.get(request.sid):
        return
    if not session['can_transmit'] and session['role'] != 'admin':
        return

    if isinstance(data, bytes) and len(data) > 0:
        from web.bot_bridge import get_bot_listener
        listener = get_bot_listener()
        if listener:
            listener.feed_web_pcm(data)


@socketio.on('ptt:stop')
def handle_ptt_stop():
    """停止 PTT 发射"""
    session = authenticated_sessions.get(request.sid)
    if not session:
        return

    # 清除 PTT 发射状态
    _ptt_active_sessions.pop(request.sid, None)

    from web.bot_bridge import get_bot_listener
    listener = get_bot_listener()
    if listener:
        listener.stop_transmit_web()

    emit('ptt:stopped')
    logger.info(f"[WS] PTT 停止: {session['username']}")


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
