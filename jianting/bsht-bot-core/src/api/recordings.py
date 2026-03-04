"""
录音 API - 录音列表、详情、播放
"""
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.database import Database


router = APIRouter()


# ===== 请求/响应模型 =====

class RecordingListResponse(BaseModel):
    """录音列表响应"""
    code: int
    message: str
    data: Optional[dict] = None


class RecordingDetailResponse(BaseModel):
    """录音详情响应"""
    code: int
    message: str
    data: Optional[dict] = None


# ===== 依赖项 =====

def get_db():
    """获取数据库实例"""
    return Database()


# ===== API 端点 =====

@router.get("/recordings")
async def get_recordings(
    page: int = 1,
    page_size: int = 20,
    date: Optional[str] = None,
    date_from: Optional[str] = None,  # 新增：日期范围开始
    date_to: Optional[str] = None,    # 新增：日期范围结束
    user_id: Optional[str] = None,
    channel_id: Optional[int] = None,
    recorder_type: Optional[str] = None,  # 新增：录音类型筛选
    min_duration: Optional[float] = None,
    signal_type: Optional[str] = None,    # 新增：信号类型筛选
    search: Optional[str] = None,
    sort_by: str = "timestamp",           # 新增：排序字段
    sort_order: str = "desc",             # 新增：排序方向
    db: Database = Depends(get_db)
):
    """
    获取录音列表

    Args:
        page: 页码
        page_size: 每页数量
        date: 日期筛选 (YYYY-MM-DD)
        date_from: 日期范围开始 (YYYY-MM-DD)
        date_to: 日期范围结束 (YYYY-MM-DD)
        user_id: 用户 ID 筛选
        channel_id: 频道 ID 筛选
        recorder_type: 录音类型筛选 (RX/TX)
        min_duration: 最小时长筛选（秒）
        signal_type: 信号类型筛选 (CQ/QSO/NOISE/UNKNOWN)
        search: 搜索关键词
        sort_by: 排序字段 (timestamp/duration/start_time)
        sort_order: 排序方向 (asc/desc)
        db: 数据库实例

    Returns:
        录音列表
    """
    # 计算偏移量
    offset = (page - 1) * page_size

    # 验证排序字段
    valid_sort_fields = ["timestamp", "duration", "start_time", "user_name"]
    if sort_by not in valid_sort_fields:
        sort_by = "timestamp"
    if sort_order not in ["asc", "desc"]:
        sort_order = "desc"

    # 使用原生 SQL 查询以支持更多筛选条件
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 构建查询
    query = "SELECT * FROM recordings WHERE 1=1"
    params = []

    if channel_id:
        query += " AND channel_id = ?"
        params.append(channel_id)

    if recorder_type:
        query += " AND recorder_type = ?"
        params.append(recorder_type)

    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)

    if date:
        query += " AND DATE(timestamp) = ?"
        params.append(date)
    elif date_from:
        query += " AND DATE(timestamp) >= ?"
        params.append(date_from)
        if date_to:
            query += " AND DATE(timestamp) <= ?"
            params.append(date_to)

    if min_duration:
        query += " AND duration >= ?"
        params.append(min_duration)

    if signal_type:
        query += " AND signal_type = ?"
        params.append(signal_type)

    if search:
        query += " AND (asr_text LIKE ? OR content_normalized LIKE ?)"
        search_pattern = f"%{search}%"
        params.append(search_pattern)
        params.append(search_pattern)

    # 添加排序
    query += f" ORDER BY {sort_by} {sort_order.upper()}"

    # 添加分页
    query += " LIMIT ? OFFSET ?"
    params.extend([page_size, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # 获取总数
    count_query = query.split("ORDER BY")[0].replace("SELECT *", "SELECT COUNT(*)")
    count_params = params[:-2]  # 排除 LIMIT 和 OFFSET
    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]

    conn.close()

    # 转换为字典
    recording_list = []
    import os
    from datetime import datetime

    for row in rows:
        # 处理音频路径
        audio_path = row[1]  # filepath
        audio_path = os.path.normpath(audio_path)
        parts = audio_path.split(os.sep)
        if "recordings" in parts:
            idx = parts.index("recordings")
            audio_path = "/".join(parts[idx:])
        else:
            try:
                timestamp_str = row[10]  # timestamp
                date_str = datetime.fromisoformat(timestamp_str).strftime("%Y-%m-%d")
                filename = row[2]  # filename
                audio_path = f"recordings/{date_str}/{filename}"
            except:
                audio_path = f"recordings/{row[2]}"

        recording_list.append({
            "id": row[0],
            "filename": row[2],
            "filepath": audio_path,
            "channel_id": row[3],
            "user_id": row[4] or "",
            "user_name": row[5] or row[4] or "",
            "recorder_type": row[6] or "",
            "duration": row[7] or 0.0,
            "start_time": row[8] or "",
            "file_size": row[9] or 0,
            "timestamp": row[10],
            "recognized": bool(row[11]),
            "asr_text": row[12] or "",
            "content_normalized": row[13] or "",
            "signal_type": row[14] or "",
            "confidence": row[15] or 0.0,
            "rms_db": row[16] or 0.0,
            "snr_db": row[17] or 0.0
        })

    return {
        "code": 0,
        "message": "success",
        "data": {
            "recordings": recording_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    }


@router.get("/recordings/stats")
async def get_recordings_stats(db: Database = Depends(get_db)):
    """
    获取录音统计信息

    Returns:
        统计数据
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 总录音数
    cursor.execute("SELECT COUNT(*) FROM recordings")
    total = cursor.fetchone()[0]

    # 今日录音数
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*) FROM recordings WHERE DATE(timestamp) = ?", (today,))
    today_count = cursor.fetchone()[0]

    # 24小时录音数
    one_day_ago = (datetime.now() - timedelta(days=1)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM recordings WHERE timestamp >= ?", (one_day_ago,))
    recent_count = cursor.fetchone()[0]

    # 识别数量
    cursor.execute("SELECT COUNT(*) FROM recordings WHERE recognized = 1")
    recognized_count = cursor.fetchone()[0]

    # 总时长（分钟）
    cursor.execute("SELECT SUM(duration) FROM recordings WHERE duration IS NOT NULL")
    total_duration = cursor.fetchone()[0] or 0
    total_duration_minutes = round(total_duration / 60, 2)

    # 平均时长
    avg_duration = round(total_duration / total, 2) if total > 0 else 0

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "total": total,
            "today": today_count,
            "recent_24h": recent_count,
            "recognized": recognized_count,
            "total_duration_minutes": total_duration_minutes,
            "avg_duration": avg_duration,
            "recognition_rate": round(recognized_count / total * 100, 2) if total > 0 else 0
        }
    }


@router.get("/recordings/stats/detailed")
async def get_recordings_stats_detailed(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    channel_id: Optional[int] = None,
    db: Database = Depends(get_db)
):
    """
    获取详细的录音统计信息

    Args:
        date_from: 日期范围开始 (YYYY-MM-DD)
        date_to: 日期范围结束 (YYYY-MM-DD)
        channel_id: 频道 ID 筛选
        db: 数据库实例

    Returns:
        详细统计数据
    """
    import sqlite3
    from datetime import datetime, timedelta

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 构建筛选条件
    where_clauses = []
    params = []

    if date_from:
        where_clauses.append("DATE(timestamp) >= ?")
        params.append(date_from)

    if date_to:
        where_clauses.append("DATE(timestamp) <= ?")
        params.append(date_to)

    if channel_id:
        where_clauses.append("channel_id = ?")
        params.append(channel_id)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # 基础统计
    stats = {}

    # 1. 总录音数和总时长
    cursor.execute(f"SELECT COUNT(*), SUM(duration), AVG(duration) FROM recordings WHERE {where_sql}")
    row = cursor.fetchone()
    stats["total"] = {
        "count": row[0],
        "total_duration": round(row[1] or 0, 2),
        "avg_duration": round(row[2] or 0, 2)
    }

    # 2. 今日录音数
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(f"SELECT COUNT(*), SUM(duration) FROM recordings WHERE DATE(timestamp) = ?", (today,))
    row = cursor.fetchone()
    stats["today"] = {
        "count": row[0],
        "total_duration": round(row[1] or 0, 2)
    }

    # 3. 识别统计
    cursor.execute(f"""
        SELECT
            COUNT(*) FILTER (WHERE recognized = 1) as recognized,
            COUNT(*) FILTER (WHERE recognized = 0) as unrecognized,
            COUNT(*) as total
        FROM recordings WHERE {where_sql}
    """)
    row = cursor.fetchone()
    stats["recognition"] = {
        "recognized": row[0],
        "unrecognized": row[1],
        "total": row[2],
        "rate": round(row[0] / row[2] * 100, 2) if row[2] > 0 else 0
    }

    # 4. 按日期统计（最近7天）
    cursor.execute(f"""
        SELECT
            DATE(timestamp) as date,
            COUNT(*) as count,
            SUM(duration) as total_duration
        FROM recordings WHERE {where_sql}
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
        LIMIT 7
    """)
    stats["by_date"] = [
        {"date": row[0], "count": row[1], "total_duration": round(row[2], 2)}
        for row in cursor.fetchall()
    ]

    # 5. 按用户统计（Top 10）
    cursor.execute(f"""
        SELECT
            COALESCE(user_name, user_id) as user_name,
            user_id,
            COUNT(*) as count,
            SUM(duration) as total_duration
        FROM recordings WHERE {where_sql}
        GROUP BY user_id, user_name
        ORDER BY count DESC
        LIMIT 10
    """)
    stats["by_user"] = [
        {"user_name": row[0], "user_id": row[1], "count": row[2], "total_duration": round(row[3], 2)}
        for row in cursor.fetchall()
    ]

    # 6. 按信号类型统计
    cursor.execute(f"""
        SELECT
            COALESCE(signal_type, 'UNKNOWN') as signal_type,
            COUNT(*) as count
        FROM recordings WHERE {where_sql}
        GROUP BY signal_type
        ORDER BY count DESC
    """)
    stats["by_signal_type"] = [
        {"signal_type": row[0], "count": row[1]}
        for row in cursor.fetchall()
    ]

    # 7. 按录音类型统计 (RX/TX)
    cursor.execute(f"""
        SELECT
            COALESCE(recorder_type, 'UNKNOWN') as recorder_type,
            COUNT(*) as count,
            SUM(duration) as total_duration
        FROM recordings WHERE {where_sql}
        GROUP BY recorder_type
        ORDER BY count DESC
    """)
    stats["by_recorder_type"] = [
        {"recorder_type": row[0], "count": row[1], "total_duration": round(row[2], 2)}
        for row in cursor.fetchall()
    ]

    # 8. 平均音频质量
    cursor.execute(f"""
        SELECT
            AVG(rms_db) as avg_rms,
            AVG(snr_db) as avg_snr,
            AVG(confidence) as avg_confidence
        FROM recordings WHERE {where_sql}
        AND rms_db IS NOT NULL
    """)
    row = cursor.fetchone()
    stats["audio_quality"] = {
        "avg_rms_db": round(row[0], 2) if row[0] else 0,
        "avg_snr_db": round(row[1], 2) if row[1] else 0,
        "avg_confidence": round(row[2], 2) if row[2] else 0
    }

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": stats
    }


@router.get("/recordings/{recording_id}")
async def get_recording_detail(
    recording_id: int,
    db: Database = Depends(get_db)
):
    """
    获取单个录音详情

    Args:
        recording_id: 录音 ID
        db: 数据库实例

    Returns:
        录音详情
    """
    import sqlite3

    # 直接查询数据库
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,))
        row = cursor.fetchone()

        if not row:
            return {
                "code": 404,
                "message": "录音不存在"
            }

        from src.database import Recording
        recording = Recording(
            id=row[0],
            filepath=row[1],
            filename=row[2],
            channel_id=row[3],
            user_id=row[4] or "",
            user_name=row[5] or "",
            recorder_type=row[6] or "",
            duration=row[7] or 0.0,
            start_time=row[8] or "",
            file_size=row[9] or 0,
            timestamp=row[10],
            recognized=bool(row[11]),
            asr_text=row[12] or "",
            content_normalized=row[13] or "",
            signal_type=row[14] or "",
            confidence=row[15] or 0.0,
            rms_db=row[16] or 0.0,
            snr_db=row[17] or 0.0,
            recognize_duration=row[18] or 0.0 if len(row) > 18 else 0.0
        )
    finally:
        conn.close()

    # 处理音频路径 - 提取相对路径
    audio_path = recording.filepath
    import os
    audio_path = os.path.normpath(audio_path)
    parts = audio_path.split(os.sep)
    if "recordings" in parts:
        idx = parts.index("recordings")
        audio_path = "/".join(parts[idx:])
    else:
        # 如果提取失败，使用文件名和日期重建路径
        try:
            from datetime import datetime
            date_str = datetime.fromisoformat(recording.timestamp).strftime("%Y-%m-%d")
            audio_path = f"recordings/{date_str}/{recording.filename}"
        except:
            audio_path = f"recordings/{recording.filename}"

    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": recording.id,
            "filename": recording.filename,
            "filepath": audio_path,  # 使用处理后的相对路径
            "channel_id": recording.channel_id,
            "user_id": recording.user_id,
            "user_name": recording.user_name or recording.user_id,
            "recorder_type": recording.recorder_type,
            "duration": recording.duration,
            "start_time": recording.start_time,
            "file_size": recording.file_size,
            "timestamp": recording.timestamp,
            "recognized": recording.recognized,
            "asr_text": recording.asr_text,
            "content_normalized": recording.content_normalized,
            "signal_type": recording.signal_type,
            "confidence": recording.confidence,
            "rms_db": recording.rms_db,
            "snr_db": recording.snr_db
        }
    }


@router.get("/recordings/dates/list")
async def get_recording_dates(db: Database = Depends(get_db)):
    """
    获取有录音的日期列表

    Args:
        db: 数据库实例

    Returns:
        日期列表
    """
    import re
    from pathlib import Path

    # 扫描 recordings 目录
    recordings_dir = Path("recordings")
    if not recordings_dir.exists():
        return {
            "code": 0,
            "message": "success",
            "data": {
                "dates": []
            }
        }

    # 获取所有日期目录
    dates = []
    for item in recordings_dir.iterdir():
        if item.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", item.name):
            dates.append(item.name)

    # 按日期降序排序
    dates.sort(reverse=True)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "dates": dates
        }
    }


@router.get("/recordings/users/list")
async def get_recording_users(db: Database = Depends(get_db)):
    """
    获取有录音的用户列表

    Args:
        db: 数据库实例

    Returns:
        用户列表
    """
    import sqlite3

    # 直接查询数据库获取所有不同的 user_id 和 user_name
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT DISTINCT user_id, user_name
            FROM recordings
            WHERE user_id IS NOT NULL AND user_id != ''
            ORDER BY user_name
        """)
        rows = cursor.fetchall()

        users = []
        for row in rows:
            users.append({
                "user_id": row[0],
                "user_name": row[1] or row[0]  # 如果没有 user_name，使用 user_id
            })
    finally:
        conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "users": users
        }
    }


@router.post("/recordings/batch-delete")
async def batch_delete_recordings(
    request_data: dict,
    db: Database = Depends(get_db)
):
    """
    批量删除录音

    Args:
        request_data: {"ids": [1, 2, 3]}
        db: 数据库实例

    Returns:
        删除结果
    """
    import sqlite3

    ids = request_data.get("ids", [])

    if not ids:
        return {
            "code": 400,
            "message": "请选择要删除的录音"
        }

    # 删除数据库记录
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    deleted_count = 0
    file_errors = []

    try:
        for rec_id in ids:
            # 先获取文件路径
            cursor.execute("SELECT filepath FROM recordings WHERE id = ?", (rec_id,))
            row = cursor.fetchone()

            if row:
                filepath = row[0]

                # 删除文件
                from pathlib import Path
                try:
                    if Path(filepath).exists():
                        Path(filepath).unlink()
                except Exception as e:
                    file_errors.append(f"{filepath}: {str(e)}")

                # 删除数据库记录
                cursor.execute("DELETE FROM recordings WHERE id = ?", (rec_id,))
                deleted_count += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

    return {
        "code": 0,
        "message": f"成功删除 {deleted_count} 条录音",
        "data": {
            "deleted_count": deleted_count,
            "file_errors": file_errors
        }
    }
