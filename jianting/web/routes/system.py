"""系统管理路由"""

import os
import psutil
from flask import Blueprint, request, jsonify
from web.middleware.auth import admin_required

system_bp = Blueprint('system', __name__, url_prefix='/api/system')


@system_bp.route('/info', methods=['GET'])
def get_info():
    """获取系统信息"""
    return jsonify({
        'platform': os.name,
        'python_version': os.sys.version,
        'hostname': os.environ.get('COMPUTERNAME', os.environ.get('HOSTNAME', 'unknown')),
    })


@system_bp.route('/status', methods=['GET'])
def get_status():
    """获取运行状态"""
    # CPU 使用率
    cpu_percent = psutil.cpu_percent(interval=0.1)

    # 内存
    memory = psutil.virtual_memory()

    # 磁盘
    disk = psutil.disk_usage('/')

    # 进程信息
    process = psutil.Process()
    process_info = {
        'pid': process.pid,
        'memory_mb': process.memory_info().rss / 1024 / 1024,
        'cpu_percent': process.cpu_percent(interval=0.1),
    }

    return jsonify({
        'cpu_percent': cpu_percent,
        'memory_total_mb': memory.total / 1024 / 1024,
        'memory_used_mb': memory.used / 1024 / 1024,
        'memory_percent': memory.percent,
        'disk_total_gb': disk.total / 1024 / 1024 / 1024,
        'disk_used_gb': disk.used / 1024 / 1024 / 1024,
        'disk_percent': disk.percent,
        'process': process_info,
    })


@system_bp.route('/restart', methods=['POST'])
@admin_required
def restart():
    """重启服务（需要管理员确认）"""
    # TODO: 实现重启逻辑
    return jsonify({'message': '重启功能待实现，需要外部进程管理器配合'})


@system_bp.route('/logs', methods=['GET'])
@admin_required
def get_logs():
    """获取日志内容"""
    # 读取最近的日志
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')

    logs = {}
    if os.path.exists(log_dir):
        for log_file in os.listdir(log_dir):
            if log_file.endswith('.log'):
                filepath = os.path.join(log_dir, log_file)
                try:
                    # 读取最后 100 行
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        logs[log_file] = ''.join(lines[-100:])
                except Exception as e:
                    logs[log_file] = f'读取失败: {str(e)}'

    return jsonify(logs)


@system_bp.route('/backup', methods=['POST'])
@admin_required
def backup():
    """数据库备份"""
    # TODO: 实现备份逻辑
    return jsonify({'message': '备份功能待实现'})
