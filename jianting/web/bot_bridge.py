"""Bot 桥接模块 — 共享 AudioStreamListener 引用

单进程架构下，BotServer 启动时将 listener 注册到此模块，
WebSocket handler 通过此模块直接调用 listener 的发射接口。
"""

import logging

# 使用项目统一日志
try:
    from src.logging_setup import get_logger
    logger = get_logger("BotBridge", "main")
except ImportError:
    logger = logging.getLogger("BotBridge")
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(logging.INFO)

# 全局 AudioStreamListener 引用 (由 bot_server.py 在连接成功后设置)
_bot_listener = None


def set_bot_listener(listener):
    """注册 Bot listener (由 bot_server.py 调用)"""
    global _bot_listener
    _bot_listener = listener
    logger.info(f"[BotBridge] listener 已注册: {type(listener).__name__}")

    # 注册 WebRTC 音频处理器
    try:
        from web.routes.webrtc import set_audio_handler
        set_audio_handler(listener)
    except Exception as e:
        logger.warning(f"[BotBridge] 注册 WebRTC 处理器失败: {e}")


def get_bot_listener():
    """获取 Bot listener (由 websocket.py 调用)"""
    return _bot_listener


def clear_bot_listener():
    """清除 Bot listener (Bot 断开时调用)"""
    global _bot_listener
    _bot_listener = None
    logger.info("[BotBridge] listener 已清除")
