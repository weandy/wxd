#!/usr/bin/env python3
"""
BSHT Bot 纯 Bot 启动脚本

只启动 Bot 服务，不包含 Web 前端：
- gRPC 客户端连接 BSHT 服务器
- 音频编解码和处理
- 录音识别（可选）
- 微信推送（可选）

启动方式:
  python run_bot.py
  或
  python run_bot.py --no-asr  # 禁用语音识别
  python run_bot.py --console-ptt  # 启用控制台 PTT
  python run_bot.py --enable-playback  # 启用音频播放（需要声卡）

服务器部署（无 PyAudio）:
  python run_bot.py  # 默认不播放，只需录制+识别+推送
"""
import sys
import os

# 强制无缓冲输出
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# Windows 控制台编码修复
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

import signal
import argparse

# 添加项目根目录到 Python 路径
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

# 配置日志
from src.logging_setup import setup_logger
logger = setup_logger("BotRunner", "bot")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='BSHT Bot 启动器')
    parser.add_argument('--no-asr', action='store_true',
                        help='禁用语音识别功能')
    parser.add_argument('--console-ptt', action='store_true',
                        help='启用控制台 PTT 按键说话')
    parser.add_argument('--enable-playback', action='store_true',
                        help='启用音频播放（需要声卡，默认不播放）')
    parser.add_argument('--username', type=str, default=None,
                        help='BSHT 用户名（覆盖 .env）')
    parser.add_argument('--password', type=str, default=None,
                        help='BSHT 密码（覆盖 .env）')
    parser.add_argument('--channel-id', type=int, default=None,
                        help='频道 ID（覆盖 .env）')
    parser.add_argument('--channel-passcode', type=str, default=None,
                        help='频道密码（覆盖 .env）')
    return parser.parse_args()


def load_config():
    """加载配置"""
    from src.config import load_env_file, get_config

    # 加载 .env 文件
    env_path = os.path.join(ROOT_DIR, '.env')
    if os.path.exists(env_path):
        load_env_file(env_path)
    else:
        # 尝试从上级目录加载
        parent_env = os.path.join(os.path.dirname(ROOT_DIR), '.env')
        if os.path.exists(parent_env):
            load_env_file(parent_env)
            logger.info("从上级目录加载配置")

    return get_config()


def init_recognizer(config):
    """初始化识别器"""
    from src.recognizer import RecordingRecognizer, create_recording_callback
    from src.database import get_database
    from src.wx_pusher import init_pusher_from_env_migration, reload_pusher, set_pusher

    logger.info("🎯 初始化伪实时识别器...")

    recognizer = RecordingRecognizer(api_key=config.api.siliconflow_key)

    # 设置数据库
    db = get_database(config.database.path)
    recognizer.set_database(db)

    # 初始化微信推送
    init_pusher_from_env_migration()
    pusher = reload_pusher()
    if pusher:
        recognizer.set_pusher(pusher)
        logger.info(f"📲 微信推送已启用 ({len(pusher.targets)} 个目标)")

    # 扫描历史录音
    logger.info("🔍 扫描历史录音文件...")
    recordings_dir = os.path.join(ROOT_DIR, 'recordings')
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)

    added, processed = recognizer.scan_and_register_recordings(recordings_dir, max_count=50)
    if added > 0 or processed > 0:
        logger.info(f"   📝 新增 {added} 条记录, 识别 {processed} 个文件")
    else:
        logger.info("   ✅ 没有需要处理的历史文件")

    # 创建回调函数
    return recognizer, create_recording_callback(recognizer)


def main():
    """主入口"""
    args = parse_args()

    logger.info("=" * 60)
    logger.info("BSHT Bot 启动 (纯 Bot 模式，无 Web 服务)")
    logger.info("=" * 60)

    # 加载配置
    config = load_config()

    # 获取配置参数（命令行参数优先）
    username = args.username or os.getenv('BSHT_USERNAME', '')
    password = args.password or os.getenv('BSHT_PASSWORD', '')
    channel_id = args.channel_id or os.getenv('BSHT_CHANNEL_ID', '')
    channel_passcode = args.channel_passcode or os.getenv('BSHT_CHANNEL_PASSCODE', '')

    if not username or not password or not channel_id:
        logger.error("❌ 请在 .env 文件中配置以下项:")
        logger.error("   BSHT_USERNAME")
        logger.error("   BSHT_PASSWORD")
        logger.error("   BSHT_CHANNEL_ID")
        return 1

    try:
        channel_id = int(channel_id)
    except ValueError:
        logger.error(f"❌ BSHT_CHANNEL_ID 必须是数字: {channel_id}")
        return 1

    logger.info(f"   用户: {username}")
    logger.info(f"   频道: {channel_id}")
    logger.info("=" * 60)

    # 导入 BotServer
    from bot_server import BotServer

    # 初始化识别器（如果启用）
    recognizer = None
    recording_callback = None

    if not args.no_asr and config.api.siliconflow_key:
        try:
            recognizer, recording_callback = init_recognizer(config)
            logger.info("✅ 识别器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 识别器初始化失败: {e}")
            logger.info("📝 将继续运行，但只录音不识别")
    elif args.no_asr:
        logger.info("📝 语音识别已禁用")
    else:
        logger.info("📝 API Key 未配置，只录制不识别")

    # 确定是否启用控制台 PTT
    enable_console_ptt = args.console_ptt or os.getenv('ENABLE_CONSOLE_PTT', '').lower() in ('1', 'true', 'yes')

    # 确定是否启用音频播放
    enable_playback = args.enable_playback or os.getenv('ENABLE_PLAYBACK', '').lower() in ('1', 'true', 'yes')

    if enable_playback:
        logger.info("🔊 音频播放: 启用 (需要声卡)")
    else:
        logger.info("🔇 音频播放: 禁用 (仅录制+识别+推送)")

    # 创建 Bot 实例
    bot = BotServer(username, password, channel_id, channel_passcode,
                    enable_console_ptt=enable_console_ptt,
                    enable_playback=enable_playback)

    # 如果有识别器，修改 BotServer 来使用回调
    if recording_callback:
        original_setup = BotServer._setup_recorder

        def new_setup(self, callback=None):
            return original_setup(self, recording_callback)

        BotServer._setup_recorder = new_setup

    # 信号处理
    def signal_handler(sig, frame):
        logger.info(f"\n收到信号 {sig}，正在关闭...")
        bot.stop()
        if recognizer:
            recognizer.shutdown(wait=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动 Bot
    try:
        logger.info("🚀 启动 Bot 服务...")
        bot.start()
    except KeyboardInterrupt:
        logger.info("收到停止信号")
    finally:
        bot.stop()
        if recognizer:
            logger.info("正在关闭识别器...")
            recognizer.shutdown(wait=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
