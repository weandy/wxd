"""
监控与系统状态 API
"""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
import psutil
import os

from src.database import Database


router = APIRouter()


# ===== 请求/响应模型 =====

class BotControl(BaseModel):
    """机器人控制请求"""
    action: str  # start, stop, restart, status


# ===== 依赖项 =====

def get_db():
    """获取数据库实例"""
    return Database()


# ===== API 端点 =====

@router.get("/monitor/overview")
async def get_monitor_overview(db: Database = Depends(get_db)):
    """
    获取监控概览数据

    Returns:
        系统概览信息
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 录音统计（24小时）
    one_day_ago = (datetime.now() - timedelta(days=1)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM recordings WHERE timestamp >= ?", (one_day_ago,))
    recordings_24h = cursor.fetchone()[0]

    # 今日识别数量
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*) FROM recordings WHERE DATE(timestamp) = ?", (today,))
    today_recordings = cursor.fetchone()[0]

    # 活跃频道数（7天内有录音）
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute("SELECT COUNT(DISTINCT channel_id) FROM recordings WHERE timestamp >= ?", (seven_days_ago,))
    active_channels_7d = cursor.fetchone()[0]

    # 系统资源使用情况
    cpu_percent = psutil.cpu_percent(interval=0)
    memory = psutil.virtual_memory()
    memory_percent = memory.percent
    memory_used = memory.used / (1024**3)  # GB
    memory_total = memory.total / (1024**3)  # GB

    # 磁盘使用情况
    disk = psutil.disk_usage('/')
    disk_used_gb = disk.used / (1024**3)
    disk_total_gb = disk.total / (1024**3)
    disk_percent = disk.percent

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "recordings_24h": recordings_24h,
            "today_recordings": today_recordings,
            "active_channels_7d": active_channels_7d,
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_used_gb": round(memory_used, 2),
                "memory_total_gb": round(memory_total, 2),
                "disk_used_gb": round(disk_used_gb, 2),
                "disk_total_gb": round(disk_total_gb, 2),
                "disk_percent": disk_percent
            },
            "uptime": get_system_uptime()
        }
    }


@router.get("/monitor/logs")
async def get_logs(
    level: Optional[str] = None,  # INFO, WARNING, ERROR
    limit: int = 100,
    offset: int = 0,
    db: Database = Depends(get_db)
):
    """
    获取系统日志

    Args:
        level: 日志级别筛选
        limit: 返回数量
        offset: 偏移量

    Returns:
        日志列表
    """
    # 这里从实际的日志文件读取
    log_file = "logs/bot.log"

    try:
        if not os.path.exists(log_file):
            return {
                "code": 0,
                "message": "success",
                "data": {
                    "logs": [],
                    "total": 0
                }
            }

        logs = []
        with open(log_file, 'r', encoding='utf-8') as f:
            # 读取最后1000行
            lines = f.readlines()
            lines = lines[-1000:]  # 只保留最后1000行

        # 筛选和格式化日志
        filtered_logs = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue

            # 简单的日志格式解析
            log_entry = parse_log_line(line)
            if log_entry:
                if level is None or log_entry.get('level') == level.upper():
                    filtered_logs.append(log_entry)

            if len(filtered_logs) >= limit + offset:
                break

        # 应用分页
        paginated_logs = filtered_logs[offset:offset + limit]

        return {
            "code": 0,
            "message": "success",
            "data": {
                "logs": paginated_logs,
                "total": len(filtered_logs),
                "limit": limit,
                "offset": offset
            }
        }
    except Exception as e:
        return {
            "code": 0,
            "message": "success",
            "data": {
                "logs": [],
                "total": 0,
                "error": str(e)
            }
        }


@router.get("/monitor/metrics")
async def get_metrics(db: Database = Depends(get_db)):
    """
    获取性能指标

    Returns:
        性能指标数据
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 定义时间变量
    today = datetime.now().strftime("%Y-%m-%d")
    one_day_ago = (datetime.now() - timedelta(days=1)).isoformat()

    # 7天趋势数据
    trend_data = []
    for i in range(7):
        date = (datetime.now() - timedelta(days=6-i)).strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT COUNT(*) FROM recordings WHERE DATE(timestamp) = ?",
            (date,)
        )
        count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM recordings WHERE DATE(timestamp) = ? AND recognized = 1",
            (date,)
        )
        recognized = cursor.fetchone()[0]

        rate = (recognized / count * 100) if count > 0 else 0

        trend_data.append({
            "date": date,
            "count": count,
            "recognized": recognized,
            "rate": round(rate, 2)
        })

    # 每小时统计（今天）
    hourly_stats = []
    for i in range(24):
        hour = f"{i:02d}"
        cursor.execute(
            "SELECT COUNT(*) FROM recordings WHERE DATE(timestamp) = ? AND CAST(strftime('%H', timestamp) AS INTEGER) = ?",
            (today, i)
        )
        count = cursor.fetchone()[0]

        hourly_stats.append({
            "hour": hour,
            "count": count
        })

    # Top 用户
    cursor.execute("""
        SELECT
            user_id,
            user_name,
            COUNT(*) as recording_count,
            SUM(duration) as total_duration
        FROM recordings
        WHERE timestamp >= ?
        GROUP BY user_id, user_name
        ORDER BY recording_count DESC
        LIMIT 10
    """, (one_day_ago,))
    top_users = []
    for row in cursor.fetchall():
        user_id, user_name, recording_count, total_duration = row
        top_users.append({
            "user_id": user_id,
            "user_name": user_name or user_id,
            "recording_count": recording_count,
            "total_duration": round(total_duration / 60, 2) if total_duration else 0
        })

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "trend_7d": trend_data,
            "hourly_stats": hourly_stats,
            "top_users": top_users
        }
    }


@router.post("/monitor/control")
async def control_bot(control: BotControl):
    """
    控制机器人（启动/停止/重启）

    Args:
        control: 控制命令

    Returns:
        控制结果
    """
    # 这里需要集成实际的机器人控制逻辑
    action = control.action

    if action == "status":
        # 获取机器人状态
        status = {
            "running": False,
            "pid": None,
            "uptime": None
        }

        # 检查是否有正在运行的机器人进程
        try:
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError("Process detection timeout")

            # 遍历所有进程，检查是否有 Bot
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    if proc.info['name'] and 'python' in proc.info['name'].lower():
                        cmdline = ' '.join(proc.info.get('cmdline') or [])
                        # 检测所有可能的 Bot 进程
                        if ('bot_server' in cmdline or
                            'multi_channel_bot' in cmdline or
                            'run_bot' in cmdline):
                            status["running"] = True
                            status["pid"] = proc.info['pid']
                            status["uptime"] = datetime.fromtimestamp(proc.info['create_time']).isoformat()
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            # 如果检测失败，返回默认状态
            pass

        return {
            "code": 0,
            "message": "success",
            "data": status
        }

    elif action == "start":
        # 启动机器人
        return {
            "code": 0,
            "message": "启动命令已发送",
            "data": {"action": "start", "status": "pending"}
        }

    elif action == "stop":
        # 停止机器人
        return {
            "code": 0,
            "message": "停止命令已发送",
            "data": {"action": "stop", "status": "pending"}
        }

    elif action == "restart":
        # 重启机器人
        return {
            "code": 0,
            "message": "重启命令已发送",
            "data": {"action": "restart", "status": "pending"}
        }

    else:
        return {
            "code": 400,
            "message": f"未知的控制命令: {action}"
        }


@router.get("/monitor/channels")
async def get_channels_status(db: Database = Depends(get_db)):
    """
    获取频道状态

    Returns:
        频道状态列表
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 获取有录音记录的频道
    cursor.execute("""
        SELECT
            channel_id,
            COUNT(*) as recording_count,
            SUM(duration) as total_duration,
            MAX(timestamp) as last_activity,
            COUNT(DISTINCT user_id) as unique_users
        FROM recordings
        WHERE timestamp >= datetime('now', '-7 days')
        GROUP BY channel_id
        ORDER BY recording_count DESC
    """)

    channels = []
    for row in cursor.fetchall():
        channel_id, recording_count, total_duration, last_activity, unique_users = row
        channels.append({
            "channel_id": channel_id,
            "recording_count": recording_count,
            "total_duration": round(total_duration / 60, 2) if total_duration else 0,
            "last_activity": last_activity,
            "unique_users": unique_users,
            "status": "active" if (datetime.now() - datetime.fromisoformat(last_activity)).seconds < 3600 else "inactive"
        })

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "channels": channels,
            "total": len(channels)
        }
    }


def get_system_uptime():
    """获取系统运行时间"""
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time

        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)

        return f"{days}天 {hours}小时 {minutes}分钟"
    except:
        return "未知"


def parse_log_line(line):
    """解析日志行"""
    import re

    # 尝试匹配标准日志格式
    # 2026-03-03 12:00:00 - INFO - module:message - log message
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+-\s+(\w+)\s+-\s+([^\-]+)\s+-\s+(.+)'

    match = re.match(pattern, line)
    if match:
        return {
            "timestamp": match.group(1),
            "level": match.group(2),
            "module": match.group(3).strip(),
            "message": match.group(4).strip()
        }

    # 尝试匹配简化格式
    if '-' in line:
        parts = line.split('-', 3)
        if len(parts) == 4:
            try:
                return {
                    "timestamp": parts[0].strip(),
                    "level": parts[1].strip().split()[0] if parts[1] else "INFO",
                    "module": parts[2].strip() if len(parts) > 2 else "",
                    "message": parts[3].strip()
                }
            except:
                pass

    return None


import time
