"""发射端 WebSocket 路由 - 音频广播"""

import struct
import logging
from web import socketio

# 使用项目统一日志
try:
    from src.logging_setup import get_logger
    logger = get_logger("TransmitterWS", "main")
except ImportError:
    logger = logging.getLogger("TransmitterWS")
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(logging.INFO)

# Web 监听客户端计数 (由 websocket.py 的 connect/disconnect 维护)
_listener_count = 0

_broadcast_frame_count = 0

def broadcast_mixed_pcm(pcm_data: bytes, sequence: int):
    """
    广播混音后的 PCM 给所有 Web 监听者

    使用 SocketIO 原生二进制传输, 无 Base64 开销
    协议: [seq:uint16][pcm_len:uint32][pcm_data:bytes]

    注意: 直接 emit 而非 start_background_task, 减少延迟抖动
    Flask-SocketIO threading 模式下跨线程 emit 是安全的
    """
    global _broadcast_frame_count

    if _listener_count <= 0:
        return

    try:
        header = struct.pack('<HI', sequence & 0xFFFF, len(pcm_data))
        payload = header + pcm_data
        _broadcast_frame_count += 1

        if _broadcast_frame_count == 1:
            logger.info(f"[转发] 首帧 PCM -> Web (listeners={_listener_count}, seq={sequence}, size={len(pcm_data)})")
        elif _broadcast_frame_count % 500 == 0:
            logger.info(f"[转发] 已发送 {_broadcast_frame_count} 帧 PCM (listeners={_listener_count})")

        socketio.emit('receive:audio', payload, namespace='/')
    except Exception as e:
        if _broadcast_frame_count <= 3:
            logger.warning(f"[转发] broadcast_mixed_pcm 失败: {e}")
        else:
            logger.debug(f"[转发] broadcast_mixed_pcm 失败: {e}")


def broadcast_channel_status(channel_id: int, channel_name: str, online_count: int):
    """广播频道状态到浏览器客户端"""
    data = {
        'channel_id': channel_id,
        'channel_name': channel_name,
        'online_count': online_count
    }
    # 使用 bot:channel 事件名，与前端 live.js 监听的一致
    def _emit():
        socketio.emit('bot:channel', data, namespace='/')
    socketio.start_background_task(_emit)
