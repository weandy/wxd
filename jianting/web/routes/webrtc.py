"""
完整的 WebRTC 信令处理模块

使用 aiortc 处理 WebRTC 连接：
- POST /api/webrtc/offer: 接收前端 offer，返回 answer
- POST /api/webrtc/ice: 处理 ICE candidate
- POST /api/webrtc/close: 关闭连接
"""

from flask import Blueprint, request, jsonify
import asyncio
import logging
import threading
from aiortc import RTCPeerConnection, RTCSessionDescription
import uuid

logger = logging.getLogger("WebRTC")

webrtc_bp = Blueprint('webrtc', __name__, url_prefix='/api/webrtc')

# 全局变量
_pcs = set()
_loop = None
_loop_thread = None
_audio_handler = None  # 音频数据处理器


def get_or_create_loop():
    """获取或创建事件循环"""
    global _loop, _loop_thread
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
        _loop_thread.start()
    return _loop


def set_audio_handler(handler):
    """设置音频处理器"""
    global _audio_handler
    _audio_handler = handler
    logger.info("[WebRTC] 音频处理器已注册")


def get_audio_handler():
    """获取音频处理器"""
    return _audio_handler


@webrtc_bp.route('/offer', methods=['POST'])
def handle_offer():
    """处理 WebRTC offer，返回 answer"""
    data = request.get_json()
    if not data or 'sdp' not in data:
        return jsonify({'error': 'Invalid offer'}), 400

    loop = get_or_create_loop()

    async def process_offer():
        pc = RTCPeerConnection()
        _pcs.add(pc)
        connection_id = str(uuid.uuid4())[:8]

        @pc.data_channel.on("onmessage")
        def on_message(message):
            # 处理接收到的音频数据
            handler = get_audio_handler()
            if handler:
                try:
                    handler.process_webrtc_audio(message.data)
                except Exception as e:
                    logger.error(f"[WebRTC] 处理音频数据错误: {e}")
            else:
                logger.warning(f"[WebRTC] 无音频处理器，丢弃 {len(message.data)} bytes")

        try:
            # 设置远程描述
            await pc.setRemoteDescription(RTCSessionDescription(
                sdp=data['sdp'],
                type='offer'
            ))

            # 创建 answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            logger.info(f"[WebRTC] 连接 {connection_id} 已建立")
            return {
                'sdp': pc.localDescription.sdp,
                'type': pc.localDescription.type
            }
        except Exception as e:
            logger.error(f"[WebRTC] 处理 offer 错误: {e}")
            return {'error': str(e)}

    # 在事件循环中运行
    try:
        future = asyncio.run_coroutine_threadsafe(process_offer(), loop)
        result = future.result(timeout=10)

        if 'error' in result:
            return jsonify(result), 500

        return jsonify(result)
    except Exception as e:
        logger.error(f"[WebRTC] 处理 offer 超时或错误: {e}")
        return jsonify({'error': str(e)}), 500


@webrtc_bp.route('/ice', methods=['POST'])
def handle_ice():
    """处理 ICE candidate"""
    # ICE candidate 处理在 WebRTC 连接建立后由 aiortc 自动处理
    return jsonify({'success': True})


@webrtc_bp.route('/close', methods=['POST'])
def handle_close():
    """关闭 WebRTC 连接"""
    global _pcs
    loop = get_or_create_loop()

    async def close_all():
        for pc in _pcs:
            await pc.close()
        _pcs.clear()

    try:
        future = asyncio.run_coroutine_threadsafe(close_all(), loop)
        future.result(timeout=5)
        logger.info("[WebRTC] 所有连接已关闭")
    except Exception as e:
        logger.error(f"[WebRTC] 关闭连接错误: {e}")

    return jsonify({'success': True})
