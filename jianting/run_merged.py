#!/usr/bin/env python3
"""
BSHT Bot 合并启动脚本 (单一进程架构)

在同一个 Flask 进程中运行 Bot 和 Web 服务：
- 共享内存状态 (BotState)
- 直接函数调用广播事件
- 无跨进程通信开销

启动方式:
  python run_merged.py
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
logger = logging.getLogger("RunMerged")


class Runner:
    """合并运行器 - 单进程架构"""

    def __init__(self):
        self.web_thread = None
        self.bot = None
        self.running = True

    def start_web(self, port: int = 8080):
        """启动 Web 服务"""
        from web import create_app, socketio

        logger.info("=" * 50)
        logger.info("🌐 启动 Web 服务...")
        logger.info(f"   访问地址: http://localhost:{port}")
        logger.info("   WebSocket: ws://localhost:{port}/bot")
        logger.info("=" * 50)

        app = create_app()

        # 在独立线程中运行 SocketIO
        def run_socketio():
            socketio.run(app, host='0.0.0.0', port=port, debug=False)

        self.web_thread = threading.Thread(target=run_socketio, daemon=True)
        self.web_thread.start()

        # 等待服务启动
        time.sleep(2)
        logger.info("✅ Web 服务已启动")

        return self.web_thread

    def start_bot(self, username: str, password: str, channel_id: int, channel_passcode: str = ""):
        """启动 Bot 服务 (与 Web 共享进程)"""
        from bot_server import BotServer
        from src.bot_state import get_bot_state

        logger.info("=" * 50)
        logger.info("🤖 启动 Bot 服务...")
        logger.info(f"   用户: {username}")
        logger.info(f"   频道: {channel_id}")
        logger.info("   模式: 共享内存 (单进程)")
        logger.info("=" * 50)

        # 初始化 Bot
        bot = BotServer(username, password, channel_id, channel_passcode)
        self.bot = bot

        # 启动 Bot
        try:
            bot.start()
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        finally:
            bot.stop()

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
        self.start_web()

        # 等待 Web 完全启动
        time.sleep(1)

        # 启动 Bot (主线程)
        self.start_bot(username, password, channel_id, channel_passcode)

    def stop(self):
        """停止所有服务"""
        logger.info("正在停止所有服务...")
        self.running = False
        if self.bot:
            self.bot.stop()


def main():
    """主入口"""
    print("=" * 60)
    print("🚀 BSHT Bot 合并启动 (单进程架构)")
    print("=" * 60)
    print("  Web:  http://localhost:8080")
    print("  Bot:  共享内存状态")
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
