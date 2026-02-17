# app.py
import os
import sys
import logging
import threading
import time
from pathlib import Path
from flask import Flask, render_template
from flask_socketio import SocketIO
from flask_cors import CORS
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

from config import Config
from database import Database, ChannelRepository, RecordingRepository
from bot_service import BotService
from ws_handler import WebSocketEventHandler, init_websocket_events
from routes.api import init_routes

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    if not Config.validate():
        logger.error("配置验证失败")
        sys.exit(1)

    Config.print_config()

    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config['SECRET_KEY'] = Config.SECRET_KEY

    CORS(app)
    socketio = SocketIO(app, cors_allowed_origins="*")

    db = Database(Config.DATABASE_PATH)
    channel_repo = ChannelRepository(db)
    recording_repo = RecordingRepository(db)

    ws_handler = WebSocketEventHandler(socketio)

    bot_service = BotService(
        username=Config.BSHT_USERNAME,
        password=Config.BSHT_PASSWORD,
        channel_repo=channel_repo,
        recording_repo=recording_repo,
        event_handler=ws_handler
    )

    init_websocket_events(socketio)
    api_bp = init_routes(bot_service, channel_repo, recording_repo)
    app.register_blueprint(api_bp)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/health')
    def health():
        return {'status': 'ok', 'bot_state': bot_service.get_status().state.value}

    app.bot_service = bot_service
    app.socketio = socketio

    return app, socketio


def start_botInBackground(bot_service: BotService):
    """在后台线程启动 Bot"""
    time.sleep(1)  # 等待服务器完全启动
    try:
        logger.info("后台启动 Bot 服务...")
        if bot_service.start():
            logger.info("Bot 启动成功")
        else:
            logger.error("Bot 启动失败")
    except Exception as e:
        logger.error(f"Bot 启动异常: {e}")
        import traceback
        logger.error(traceback.format_exc())


def main():
    Path(Config.RECORDINGS_PATH).mkdir(parents=True, exist_ok=True)

    app, socketio = create_app()

    # 在后台线程启动 Bot
    bot_thread = threading.Thread(
        target=start_botInBackground,
        args=(app.bot_service,),
        daemon=True
    )
    bot_thread.start()

    logger.info(f"启动服务器: {Config.HOST}:{Config.PORT}")
    logger.info("访问 http://localhost:5000 打开管理界面")

    try:
        socketio.run(
            app,
            host=Config.HOST,
            port=Config.PORT,
            debug=Config.DEBUG
        )
    except KeyboardInterrupt:
        logger.info("收到退出信号，正在关闭...")
        app.bot_service.stop()


if __name__ == '__main__':
    main()
