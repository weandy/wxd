"""
Bot WebSocket 客户端 - 连接到 Web 服务，推送实时状态
"""
import asyncio
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
    """Bot WebSocket 客户端"""

    def __init__(self, ws_url: str = "ws://localhost:8080/bot"):
        self.ws_url = ws_url
        self.ws = None
        self.running = False
        self.connected = False
        self.reconnect_delay = 5  # 重连延迟(秒)
        self._thread: Optional[threading.Thread] = None
        self._callbacks = {}  # 回调函数

        # 回调函数注册
        self._callbacks['on_command'] = []

    def connect(self) -> bool:
        """连接到 WebSocket 服务器"""
        try:
            import websocket
            logger.info(f"[WS] 连接到 {self.ws_url}...")

            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_pong=self._on_pong
            )

            # 运行在独立线程
            self.running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

            logger.info("[WS] 连接线程已启动")
            return True

        except ImportError:
            logger.warning("[WS] websocket-client 未安装，跳过连接")
            return False
        except Exception as e:
            logger.error(f"[WS] 连接失败: {e}")
            return False

    def _run(self):
        """WebSocket 运行循环"""
        while self.running:
            try:
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                logger.error(f"[WS] 运行异常: {e}")

            if self.running:
                logger.info(f"[WS] 断开连接，{self.reconnect_delay}秒后重连...")
                time.sleep(self.reconnect_delay)

    def _on_open(self, ws):
        """连接打开"""
        logger.info("[WS] ✅ 已连接到 Web 服务")
        self.connected = True

        # 发送认证消息
        ws.send(json.dumps({
            'type': 'bot:auth',
            'data': {
                'bot_name': 'BSHT Bot',
                'version': '1.0'
            }
        }))

    def _on_message(self, ws, message):
        """收到消息"""
        try:
            data = json.loads(message)
            msg_type = data.get('type', '')

            logger.debug(f"[WS] 收到消息: {msg_type}")

            if msg_type == 'bot:command':
                # 处理控制指令
                for callback in self._callbacks['on_command']:
                    callback(data.get('data', {}))

        except json.JSONDecodeError:
            logger.warning(f"[WS] 收到无效 JSON: {message[:100]}")

    def _on_error(self, ws, error):
        """连接错误"""
        logger.error(f"[WS] 错误: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """连接关闭"""
        logger.warning(f"[WS] 连接关闭: {close_status_code} - {close_msg}")
        self.connected = False

    def _on_pong(self, ws, data):
        """收到 Pong"""
        logger.debug("[WS] 收到 Pong")

    def disconnect(self):
        """断开连接"""
        logger.info("[WS] 断开连接...")
        self.running = False
        if self.ws:
            self.ws.close()
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
            self.ws.send(json.dumps({
                'type': 'bot:status',
                'data': status
            }))
            logger.debug(f"[WS] 推送状态: {status.get('running', False)}")
        except Exception as e:
            logger.warning(f"[WS] 推送状态失败: {e}")

    def push_channel(self, channel_id: int, channel_name: str, online_count: int):
        """推送频道状态"""
        if not self.connected:
            return
        try:
            self.ws.send(json.dumps({
                'type': 'bot:channel',
                'data': {
                    'channel_id': channel_id,
                    'channel_name': channel_name,
                    'online_count': online_count
                }
            }))
            logger.info(f"[WS] 推送频道: {channel_name} ({online_count}人在线)")
        except Exception as e:
            logger.warning(f"[WS] 推送频道失败: {e}")

    def push_recording(self, recording: dict):
        """推送新录音"""
        if not self.connected:
            return
        try:
            self.ws.send(json.dumps({
                'type': 'bot:recording',
                'data': recording
            }))
            logger.info(f"[WS] 推送录音: {recording.get('filename', 'unknown')}")
        except Exception as e:
            logger.warning(f"[WS] 推送录音失败: {e}")

    def push_speaking(self, user_id: str, user_name: str, speaking: bool):
        """推送说话状态"""
        if not self.connected:
            return
        try:
            self.ws.send(json.dumps({
                'type': 'bot:speaking',
                'data': {
                    'user_id': user_id,
                    'user_name': user_name,
                    'speaking': speaking
                }
            }))
            status = "开始说话" if speaking else "停止说话"
            logger.debug(f"[WS] 推送说话状态: {user_name} {status}")
        except Exception as e:
            logger.warning(f"[WS] 推送说话状态失败: {e}")


def get_bot_ws_client() -> Optional[BotWSClient]:
    """获取全局 Bot WebSocket 客户端"""
    global _bot_ws_client
    return _bot_ws_client


def init_bot_ws_client(ws_url: str = "ws://localhost:8080/bot") -> BotWSClient:
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
