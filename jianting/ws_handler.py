# ws_handler.py
import logging
import time
from flask import request
from flask_socketio import SocketIO, emit, join_room, leave_room
from interfaces import IEventHandler, BotStatus

logger = logging.getLogger(__name__)


class WebSocketEventHandler(IEventHandler):
    """WebSocket 事件处理器"""

    def __init__(self, socketio: SocketIO):
        self._socketio = socketio

    def on_audio_recorded(self, recording):
        self._socketio.emit('audio_recorded', {
            'id': recording.id,
            'channel_id': recording.channel_id,
            'speaker_name': recording.speaker_name,
            'start_time': recording.start_time.isoformat() if recording.start_time else None,
            'duration_sec': recording.duration_sec,
            'file_path': recording.file_path
        }, namespace='/bot')

    def on_message_received(self, channel_id: int, user_id: int, content: str):
        self._socketio.emit('message_received', {
            'channel_id': channel_id,
            'user_id': user_id,
            'content': content
        }, namespace='/bot')

    def on_speaker_started(self, channel_id: int, user_id: int, username: str):
        self._socketio.emit('speaker_started', {
            'channel_id': channel_id,
            'user_id': user_id,
            'username': username
        }, namespace='/bot')

    def on_speaker_stopped(self, channel_id: int, user_id: int):
        self._socketio.emit('speaker_stopped', {
            'channel_id': channel_id,
            'user_id': user_id
        }, namespace='/bot')

    def on_transmit_started(self):
        self._socketio.emit('transmit_started', {}, namespace='/bot')

    def on_transmit_stopped(self):
        self._socketio.emit('transmit_stopped', {}, namespace='/bot')

    def on_bot_state_changed(self, status: BotStatus):
        self._socketio.emit('bot_status_changed', {
            'state': status.state.value,
            'connected_channel': status.connected_channel,
            'is_transmitting': status.is_transmitting,
            'current_speakers': status.current_speakers,
            'error_message': status.error_message
        }, namespace='/bot')


def init_websocket_events(socketio: SocketIO):
    """初始化 WebSocket 事件处理"""

    @socketio.on('connect', namespace='/bot')
    def handle_connect():
        logger.info(f"客户端连接: {request.sid}")
        join_room('bot_clients')

    @socketio.on('disconnect', namespace='/bot')
    def handle_disconnect():
        logger.info(f"客户端断开: {request.sid}")
        leave_room('bot_clients')

    @socketio.on('ping', namespace='/bot')
    def handle_ping():
        emit('pong', {'timestamp': time.time()}, namespace='/bot')
