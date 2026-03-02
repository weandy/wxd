"""
仪表盘 API - 统计数据和图表
"""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.database import Database


router = APIRouter()


# ===== 请求/响应模型 =====

class OverviewResponse(BaseModel):
    """概览数据响应"""
    code: int
    message: str
    data: Optional[dict] = None


class TrendResponse(BaseModel):
    """趋势数据响应"""
    code: int
    message: str
    data: Optional[dict] = None


class SignalTypesResponse(BaseModel):
    """信号类型分布响应"""
    code: int
    message: str
    data: Optional[dict] = None


class TopUsersResponse(BaseModel):
    """活跃用户排行响应"""
    code: int
    message: str
    data: Optional[dict] = None


# ===== 依赖项 =====

def get_db():
    """获取数据库实例"""
    return Database()


# ===== API 端点 =====

@router.get("/dashboard/overview")
async def get_overview(db: Database = Depends(get_db)):
    """
    获取概览数据

    Returns:
        总录音数、增长率、活跃用户、总时长等
    """
    import sqlite3
    from datetime import datetime, timedelta

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 总录音数
    cursor.execute("SELECT COUNT(*) FROM recordings")
    total_recordings = cursor.fetchone()[0]

    # 已识别录音数
    cursor.execute("SELECT COUNT(*) FROM recordings WHERE recognized = 1")
    recognized_count = cursor.fetchone()[0]

    # 识别率
    recognition_rate = (recognized_count / total_recordings * 100) if total_recordings > 0 else 0

    # 总时长（秒）
    cursor.execute("SELECT SUM(duration) FROM recordings")
    total_duration = cursor.fetchone()[0] or 0

    # 活跃用户数（7天内有录音的用户）
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute(
        "SELECT COUNT(DISTINCT user_id) FROM recordings WHERE timestamp >= ?",
        (seven_days_ago,)
    )
    active_users_7d = cursor.fetchone()[0]

    # 今日录音数
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT COUNT(*) FROM recordings WHERE DATE(timestamp) = ?",
        (today,)
    )
    today_recordings = cursor.fetchone()[0]

    # 昨日录音数
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT COUNT(*) FROM recordings WHERE DATE(timestamp) = ?",
        (yesterday,)
    )
    yesterday_recordings = cursor.fetchone()[0]

    # 增长率（今日 vs 昨日）
    if yesterday_recordings > 0:
        growth_rate = ((today_recordings - yesterday_recordings) / yesterday_recordings) * 100
    else:
        growth_rate = 0

    # 信号类型分布
    cursor.execute("""
        SELECT signal_type, COUNT(*) as count
        FROM recordings
        WHERE signal_type IS NOT NULL AND signal_type != ''
        GROUP BY signal_type
        ORDER BY count DESC
    """)
    signal_types = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "total_recordings": total_recordings,
            "recognized_count": recognized_count,
            "recognition_rate": round(recognition_rate, 2),
            "total_duration": round(total_duration / 60, 2),  # 转换为分钟
            "active_users_7d": active_users_7d,
            "today_recordings": today_recordings,
            "yesterday_recordings": yesterday_recordings,
            "growth_rate": round(growth_rate, 2),
            "signal_types": signal_types
        }
    }


@router.get("/dashboard/trend")
async def get_trend(
    days: int = 7,
    db: Database = Depends(get_db)
):
    """
    获取趋势数据

    Args:
        days: 天数（默认7天）
        db: 数据库实例

    Returns:
        每日录音数、识别率趋势
    """
    import sqlite3
    from datetime import datetime, timedelta

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 生成日期列表
    date_list = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        date_list.append(date)

    date_list.reverse()  # 从早到晚排序

    # 查询每日数据
    daily_data = []
    for date in date_list:
        cursor.execute(
            "SELECT COUNT(*) FROM recordings WHERE DATE(timestamp) = ?",
            (date,)
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM recordings WHERE DATE(timestamp) = ? AND recognized = 1",
            (date,)
        )
        recognized = cursor.fetchone()[0]

        rate = (recognized / total * 100) if total > 0 else 0

        daily_data.append({
            "date": date,
            "total": total,
            "recognized": recognized,
            "rate": round(rate, 2)
        })

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "days": days,
            "data": daily_data
        }
    }


@router.get("/dashboard/signal-types")
async def get_signal_types(db: Database = Depends(get_db)):
    """
    获取信号类型分布

    Returns:
        信号类型统计数据
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COALESCE(signal_type, 'UNKNOWN') as signal_type,
            COUNT(*) as count,
            SUM(duration) as total_duration
        FROM recordings
        GROUP BY signal_type
        ORDER BY count DESC
    """)

    rows = cursor.fetchall()

    signal_types = []
    for row in rows:
        signal_type, count, total_duration = row
        signal_types.append({
            "type": signal_type,
            "count": count,
            "duration": round(total_duration / 60, 2) if total_duration else 0  # 转换为分钟
        })

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "signal_types": signal_types
        }
    }


@router.get("/dashboard/top-users")
async def get_top_users(
    limit: int = 10,
    db: Database = Depends(get_db)
):
    """
    获取活跃用户排行

    Args:
        limit: 返回数量（默认10）
        db: 数据库实例

    Returns:
        活跃用户排行榜
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            user_id,
            user_name,
            COUNT(*) as recording_count,
            SUM(duration) as total_duration,
            MAX(timestamp) as last_active
        FROM recordings
        GROUP BY user_id, user_name
        ORDER BY recording_count DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()

    top_users = []
    for row in rows:
        user_id, user_name, recording_count, total_duration, last_active = row
        top_users.append({
            "user_id": user_id,
            "user_name": user_name or user_id,
            "recording_count": recording_count,
            "total_duration": round(total_duration / 60, 2),  # 转换为分钟
            "last_active": last_active
        })

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "top_users": top_users
        }
    }
