# app.py
import os
import sys
import logging
from pathlib import Path
from flask import Flask, render_template
from flask_socketio import SocketIO
from flask_cors import CORS

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

    @app.before_request
    def startup_bot():
        if not hasattr(app, '_bot_started'):
            logger.info("自动启动 Bot 服务...")
            if bot_service.start():
                logger.info("Bot 启动成功")
            else:
                logger.error("Bot 启动失败")
            app._bot_started = True

    app.bot_service = bot_service
    app.socketio = socketio

    return app, socketio


def main():
    Path(Config.RECORDINGS_PATH).mkdir(parents=True, exist_ok=True)

    app, socketio = create_app()

    logger.info(f"启动服务器: {Config.HOST}:{Config.PORT}")

    try:
        socketio.run(
            app,
            host=Config.HOST,
            port=Config.PORT,
            debug=Config.DEBUG,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        logger.info("收到退出信号，正在关闭...")
        app.bot_service.stop()


if __name__ == '__main__':
    main()
