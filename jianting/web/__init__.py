"""Flask 应用工厂"""
from flask import Flask
from flask_socketio import SocketIO
import os
import sys

# 确保项目根目录在 Python 路径中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

socketio = SocketIO()


def create_app():
    """创建并配置 Flask 应用"""
    app = Flask(__name__)

    # 配置
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB 上传限制

    # 数据库路径
    app.config['DATABASE_PATH'] = os.getenv(
        'DATABASE_PATH',
        os.path.join(ROOT_DIR, 'data', 'records.db')
    )

    # 初始化 SocketIO - 使用 threading 模式避免 eventlet greenlet 问题
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    # 执行数据库迁移
    from web.models.migration import migrate
    migrate(app.config['DATABASE_PATH'])

    # 初始化默认管理员
    from web.models.database import init_default_admin
    init_default_admin(app.config['DATABASE_PATH'])

    # 注册蓝图 (按依赖顺序)
    from web.routes.auth import auth_bp
    from web.routes.bot import bot_bp
    from web.routes.recordings import recordings_bp
    from web.routes.system import system_bp
    from web.routes.channels import channels_bp
    from web.routes.users import users_bp
    from web.routes.audio_library import audio_library_bp
    from web.routes.scheduled_tasks import scheduled_tasks_bp
    from web.routes.config import config_bp
    from web.routes.notify import notify_bp
    from web.routes.correction import correction_bp
    from web.routes.data_maintenance import data_maintenance_bp
    from web.routes.audit_logs import audit_logs_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(bot_bp, url_prefix='/api/bot')
    app.register_blueprint(recordings_bp, url_prefix='/api/recordings')
    app.register_blueprint(system_bp, url_prefix='/api/system')
    app.register_blueprint(channels_bp, url_prefix='/api/channels')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(audio_library_bp, url_prefix='/api/audio-library')
    app.register_blueprint(scheduled_tasks_bp, url_prefix='/api/scheduled-tasks')
    app.register_blueprint(config_bp, url_prefix='/api/config')
    app.register_blueprint(notify_bp, url_prefix='/api/notify')
    app.register_blueprint(correction_bp, url_prefix='/api/correction')
    app.register_blueprint(data_maintenance_bp)
    app.register_blueprint(audit_logs_bp)

    # 页面路由
    from web.routes.pages import pages_bp
    app.register_blueprint(pages_bp)

    # 注册 WebSocket 事件处理
    import web.routes.websocket  # noqa: F401
    import web.routes.transmitter  # noqa: F401

    return app
