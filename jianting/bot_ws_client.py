"""
Bot WebSocket 客户端 - 使用 Socket.IO 协议连接到 Web 服务
"""
import json
import threading
import time
import os
import logging
from typing import Optional, Callable

logger = logging.getLogger("BotWSClient")

# 全局客户端实例
_bot_ws_client: Optional['BotWSClient'] = None
_bot_ws_client_lock = threading.Lock()


class BotWSClient:
    """Bot Socket.IO 客户端"""

    def __init__(self, ws_url: str = "http://localhost:8080"):
        # 转换为 Socket.IO URL
        self.ws_url = ws_url
        self.socket_url = ws_url.replace('ws://', 'http://').replace('wss://', 'https://')
        self.io = None
        self.running = False
        self.connected = False
        self.reconnect_delay = 5  # 重连延迟(秒)
        self._thread: Optional[threading.Thread] = None
        self._callbacks = {}  # 回调函数

        # 回调函数注册
        self._callbacks['on_command'] = []

    def connect(self) -> bool:
        """连接到 Socket.IO 服务器"""
        try:
            import socketio
            logger.info(f"[WS] 连接到 {self.socket_url}...")

            # 创建 Socket.IO 客户端
            self.io = socketio.Client(reconnection=True, reconnection_attempts=0)

            # 注册事件处理 - 使用默认 namespace
            self.io.on('connect', self._on_connect)
            self.io.on('disconnect', self._on_disconnect)
            self.io.on('bot_connected', self._on_bot_connected)
            self.io.on('bot_auth_ok', self._on_auth_ok)
            self.io.on('bot_command', self._on_command)

            # 连接 - 尝试 websocket，如果失败则降级到 polling
            try:
                self.io.connect(
                    self.socket_url,
                    transports=['websocket', 'polling']
                )
            except:
                # 如果 websocket 失败，使用 polling
                self.io.connect(
                    self.socket_url,
                    transports=['polling']
                )

            self.running = True
            logger.info("[WS] 连接线程已启动")
            return True

        except ImportError:
            logger.warning("[WS] python-socketio 未安装，跳过连接")
            return False
        except Exception as e:
            logger.error(f"[WS] 连接失败: {e}")
            return False

    def _on_connect(self):
        """连接成功"""
        logger.info("[WS] ✅ 已连接到 Web 服务")
        self.connected = True

    def _on_disconnect(self):
        """断开连接"""
        logger.warning("[WS] 连接断开")
        self.connected = False

    def _on_bot_connected(self, data):
        """Bot 连接确认"""
        logger.info(f"[WS] Bot 已连接: {data}")
        self.connected = True

        # 发送认证 - 使用默认 namespace
        self.io.emit('bot_auth', {
            'bot_name': 'BSHT Bot',
            'version': '1.0'
        })

    def _on_auth_ok(self, data):
        """认证成功"""
        logger.info("[WS] ✅ Bot 认证成功")
        self.connected = True

    def _on_command(self, data):
        """收到命令"""
        logger.info(f"[WS] 收到命令: {data}")
        for callback in self._callbacks['on_command']:
            callback(data)

    def disconnect(self):
        """断开连接"""
        logger.info("[WS] 断开连接...")
        self.running = False
        if self.io:
            try:
                self.io.disconnect()
            except:
                pass
        self.connected = False

    def register_command_callback(self, callback: Callable):
        """注册命令回调"""
        self._callbacks['on_command'].append(callback)

    # ===== 推送方法 =====

    def push_status(self, status: dict):
        """推送 Bot 状态"""
        if not self.connected:
            return
        try:
            self.io.emit('bot_status', status)
            logger.debug(f"[WS] 推送状态: {status.get('running', False)}")
        except Exception as e:
            logger.warning(f"[WS] 推送状态失败: {e}")

    def push_channel(self, channel_id: int, channel_name: str, online_count: int):
        """推送频道状态"""
        if not self.connected:
            return
        try:
            self.io.emit('bot_channel', {
                'channel_id': channel_id,
                'channel_name': channel_name,
                'online_count': online_count
            })
            logger.info(f"[WS] 推送频道: {channel_name} ({online_count}人在线)")
        except Exception as e:
            logger.warning(f"[WS] 推送频道失败: {e}")

    def push_recording(self, recording: dict):
        """推送新录音"""
        if not self.connected:
            return
        try:
            self.io.emit('bot_recording', recording)
            logger.info(f"[WS] 推送录音: {recording.get('filename', 'unknown')}")
        except Exception as e:
            logger.warning(f"[WS] 推送录音失败: {e}")

    def push_speaking(self, user_id: str, user_name: str, speaking: bool):
        """推送说话状态"""
        if not self.connected:
            return
        try:
            self.io.emit('bot_speaking', {
                'user_id': user_id,
                'user_name': user_name,
                'speaking': speaking
            })
            status = "开始说话" if speaking else "停止说话"
            logger.debug(f"[WS] 推送说话状态: {user_name} {status}")
        except Exception as e:
            logger.warning(f"[WS] 推送说话状态失败: {e}")


def get_bot_ws_client() -> Optional[BotWSClient]:
    """获取全局 Bot WebSocket 客户端"""
    global _bot_ws_client
    return _bot_ws_client


def init_bot_ws_client(ws_url: str = "http://localhost:8080") -> BotWSClient:
    """初始化 Bot WebSocket 客户端"""
    global _bot_ws_client

    with _bot_ws_client_lock:
        if _bot_ws_client is None:
            _bot_ws_client = BotWSClient(ws_url)
        return _bot_ws_client


if __name__ == "__main__":
    # 测试连接
    logging.basicConfig(level=logging.INFO)

    client = BotWSClient()
    client.connect()

    # 模拟推送
    time.sleep(2)
    if client.connected:
        client.push_status({'running': True, 'uptime': '10s'})
        client.push_channel(62793, '测试频道', 5)

    # 等待后关闭
    time.sleep(3)
    client.disconnect()
