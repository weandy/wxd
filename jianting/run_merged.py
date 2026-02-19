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
        from src.config import get_config
        from src.recognizer import RecordingRecognizer, create_recording_callback
        from src.database import get_database
        from src.wx_pusher import load_pusher

        logger.info("=" * 50)
        logger.info("🤖 启动 Bot 服务...")
        logger.info(f"   用户: {username}")
        logger.info(f"   频道: {channel_id}")
        logger.info("   模式: 共享内存 (单进程)")
        logger.info("=" * 50)

        config = get_config()

        # 初始化识别器
        recognizer = None
        recording_callback = None
        if config.dsp.enabled and config.api.siliconflow_key:
            logger.info("🎯 初始化伪实时识别器...")

            recognizer = RecordingRecognizer(
                api_key=config.api.siliconflow_key,
                dsp_config={
                    "algorithm": config.dsp.algorithm,
                    "agc_mode": config.dsp.agc_mode,
                    "snr_threshold_high": config.dsp.snr_threshold_high,
                    "snr_threshold_low": config.dsp.snr_threshold_low,
                    "expert_model": config.api.expert_model if config.api.expert_model_enabled else "glm-4-flash",
                    "zhipu_key": config.api.zhipu_key,
                    "zhipu_base_url": config.api.zhipu_base_url
                }
            )

            # 设置数据库
            db = get_database(config.database.path)
            recognizer.set_database(db)

            # 初始化微信推送器
            pusher = load_pusher()
            if pusher:
                recognizer.set_pusher(pusher)
                logger.info(f"📲 微信推送已启用 ({len(pusher.targets)} 个目标)")

            # 扫描历史录音
            logger.info("🔍 扫描历史录音文件...")
            added, processed = recognizer.scan_and_register_recordings("recordings", max_count=50)
            if added > 0 or processed > 0:
                logger.info(f"   📝 新增 {added} 条记录, 识别 {processed} 个文件")
            else:
                logger.info("   ✅ 没有需要处理的历史文件")

            # 创建回调函数
            recording_callback = create_recording_callback(recognizer, channel_id)
            logger.info("✅ 识别器已初始化")

        # 初始化 Bot
        bot = BotServer(username, password, channel_id, channel_passcode)

        # 如果有识别器，修改 BotServer 来使用回调
        if recording_callback:
            original_setup = BotServer._setup_recorder

            def new_setup(self, callback=None):
                return original_setup(self, recording_callback)

            BotServer._setup_recorder = new_setup

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
