"""页面路由 — 返回 Jinja2 模板"""

from flask import Blueprint, render_template, redirect, url_for, request

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    """首页重定向到登录"""
    return redirect(url_for('pages.login_page'))


@pages_bp.route('/login')
def login_page():
    """登录页面"""
    return render_template('login.html')


@pages_bp.route('/dashboard')
def dashboard_page():
    """仪表盘页面"""
    return render_template('dashboard.html')


@pages_bp.route('/recordings')
def recordings_page():
    """录音管理页面"""
    return render_template('recordings.html')


@pages_bp.route('/channels')
def channels_page():
    """频道管理页面"""
    return render_template('channels.html')


@pages_bp.route('/users')
def users_page():
    """用户管理页面"""
    return render_template('users.html')


@pages_bp.route('/audio-library')
def audio_library_page():
    """音频库页面"""
    return render_template('audio_library.html')


@pages_bp.route('/live')
def live_page():
    """实时通话页面"""
    return render_template('live.html')


@pages_bp.route('/audio-realtime')
def audio_realtime_page():
    """实时音频页面"""
    return render_template('audio_realtime.html')


@pages_bp.route('/scheduled-tasks')
def scheduled_tasks_page():
    """定时任务页面"""
    return render_template('scheduled_tasks.html')


@pages_bp.route('/notify')
def notify_page():
    """通知推送管理页面"""
    return render_template('notify.html')


@pages_bp.route('/data-maintenance')
def data_maintenance_page():
    """数据维护页面"""
    return render_template('data_maintenance.html')


@pages_bp.route('/audit-logs')
def audit_logs_page():
    """操作日志页面"""
    return render_template('audit_logs.html')


@pages_bp.route('/monitor')
def monitor_page():
    """系统监控页面"""
    return render_template('monitor.html')


@pages_bp.route('/settings')
def settings_page():
    """系统设置页面"""
    return render_template('settings.html')


@pages_bp.route('/correction')
def correction_page():
    """纠错规则管理页面"""
    return render_template('correction.html')
