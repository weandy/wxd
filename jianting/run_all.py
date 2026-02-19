#!/usr/bin/env python3
"""
BSHT Bot 整合启动脚本

同时启动 Web 服务和 Bot 服务，通过 WebSocket 实时通信：
- Bot 推送状态给 Web (bot:status, bot:channel, bot:recording, bot:speaking)
- Web 推送控制指令给 Bot (bot:command)
- Web 转发事件给浏览器客户端
"""
import os
import sys
import signal
import threading
import time
import logging

# 添加项目根目录到 Python 路径
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("RunAll")


class Runner:
    """整合运行器"""

    def __init__(self):
        self.web_server = None
        self.bot_client = None
        self.running = True

    def start_web(self, port: int = 8080):
        """启动 Web 服务"""
        from web import create_app, socketio

        logger.info(f"=" * 50)
        logger.info(f"🌐 启动 Web 服务...")
        logger.info(f"   访问地址: http://localhost:{port}")
        logger.info(f"   WebSocket: ws://localhost:{port}/bot")
        logger.info(f"=" * 50)

        app = create_app()

        # 在独立线程中运行 SocketIO
        def run_socketio():
            socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)

        thread = threading.Thread(target=run_socketio, daemon=True)
        thread.start()

        # 等待服务启动
        time.sleep(2)
        logger.info("✅ Web 服务已启动")

        return thread

    def start_bot(self, username: str, password: str, channel_id: int, channel_passcode: str = ""):
        """启动 Bot 服务"""
        logger.info(f"=" * 50)
        logger.info(f"🤖 启动 Bot 服务...")
        logger.info(f"   用户: {username}")
        logger.info(f"   频道: {channel_id}")
        logger.info(f"=" * 50)

        # 初始化 Bot WebSocket 客户端
        from bot_ws_client import init_bot_ws_client, get_bot_ws_client

        ws_url = os.getenv('BOT_WS_URL', 'ws://localhost:8080/bot')
        self.bot_client = init_bot_ws_client(ws_url)

        # 启动 Bot
        from bot_server import BotServer

        bot = BotServer(username, password, channel_id, channel_passcode)

        # 注册命令回调
        def on_command(data):
            cmd = data.get('command', '')
            logger.info(f"[Bot] 收到命令: {cmd}")
            # TODO: 执行命令

        self.bot_client.register_command_callback(on_command)

        # 连接 WebSocket
        self.bot_client.connect()

        # 等待连接
        for i in range(10):
            time.sleep(0.5)
            if self.bot_client.connected:
                logger.info("✅ Bot 已连接到 Web 服务")
                break

        # 启动 Bot
        try:
            bot.start()
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        finally:
            bot.stop()
            self.bot_client.disconnect()

    def run(self):
        """运行所有服务"""
        # 读取配置
        from src.config import load_env_file
        load_env_file('.env')

        username = os.getenv('BSHT_USERNAME', '')
        password = os.getenv('BSHT_PASSWORD', '')
        channel_id = os.getenv('BSHT_CHANNEL_ID', '')
        channel_passcode = os.getenv('BSHT_CHANNEL_PASSCODE', '')

        if not username or not password or not channel_id:
            logger.error("❌ 请在 .env 文件中配置 BSHT_USERNAME, BSHT_PASSWORD, BSHT_CHANNEL_ID")
            return

        try:
            channel_id = int(channel_id)
        except ValueError:
            logger.error(f"❌ BSHT_CHANNEL_ID 必须是数字: {channel_id}")
            return

        # 启动 Web (后台线程)
        web_thread = self.start_web()

        # 启动 Bot (主线程)
        self.start_bot(username, password, channel_id, channel_passcode)

    def stop(self):
        """停止所有服务"""
        logger.info("正在停止所有服务...")
        self.running = False


def main():
    """主入口"""
    print("=" * 60)
    print("🚀 BSHT Bot 整合启动")
    print("=" * 60)
    print("  模式: Bot + Web 合并启动 (WebSocket 通信)")
    print("  Web:  http://localhost:8080")
    print("  Bot:  ws://localhost:8080/bot")
    print("=" * 60)

    runner = Runner()

    # 信号处理
    def signal_handler(sig, frame):
        logger.info(f"\n收到信号 {sig}，正在关闭...")
        runner.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        runner.run()
    except Exception as e:
        logger.exception(f"运行异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
