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
    user_id: Optional[str] = None,
    channel_id: Optional[int] = None,
    min_duration: Optional[float] = None,
    search: Optional[str] = None,
    db: Database = Depends(get_db)
):
    """
    获取录音列表

    Args:
        page: 页码
        page_size: 每页数量
        date: 日期筛选 (YYYY-MM-DD)
        user_id: 用户 ID 筛选
        channel_id: 频道 ID 筛选
        min_duration: 最小时长筛选（秒）
        search: 搜索关键词
        db: 数据库实例

    Returns:
        录音列表
    """
    # 计算偏移量
    offset = (page - 1) * page_size

    # 构建查询参数
    recognized = None  # 不筛选识别状态

    # 获取录音列表
    recordings = db.get_recordings(
        channel_id=channel_id,
        recognized=recognized,
        user_id=user_id,
        date=date,
        min_duration=min_duration,
        search=search,
        limit=page_size,
        offset=offset
    )

    # 转换为字典
    recording_list = []
    for rec in recordings:
        # 处理音频路径 - 返回相对于项目根目录的路径
        # web_server.py 已经挂载了 /recordings 到 recordings 目录
        # 所以只需要返回 recordins/日期/文件名 的格式
        audio_path = rec.filepath

        # 标准化路径：提取 "recordings/" 之后的部分
        import os
        audio_path = os.path.normpath(audio_path)  # 标准化路径

        # 查找 "recordings" 在路径中的位置
        parts = audio_path.split(os.sep)
        if "recordings" in parts:
            # 从 "recordings" 开始截取
            idx = parts.index("recordings")
            audio_path = "/".join(parts[idx:])  # 用正斜杠连接（URL 标准）

        # 确保 URL 路径格式正确
        if not audio_path.startswith("recordings/"):
            # 如果提取失败，使用文件名和日期重建路径
            from datetime import datetime
            try:
                date_str = datetime.fromisoformat(rec.timestamp).strftime("%Y-%m-%d")
                audio_path = f"recordings/{date_str}/{rec.filename}"
            except:
                audio_path = f"recordings/{rec.filename}"

        recording_list.append({
            "id": rec.id,
            "filename": rec.filename,
            "filepath": audio_path,  # 使用处理后的相对路径
            "channel_id": rec.channel_id,
            "user_id": rec.user_id,
            "user_name": rec.user_name or rec.user_id,
            "recorder_type": rec.recorder_type,
            "duration": rec.duration,
            "start_time": rec.start_time,
            "file_size": rec.file_size,
            "timestamp": rec.timestamp,
            "recognized": rec.recognized,
            "asr_text": rec.asr_text,
            "content_normalized": rec.content_normalized,
            "signal_type": rec.signal_type,
            "confidence": rec.confidence
        })

    # 获取总数 - 需要单独查询以获取正确的总记录数
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 构建计数查询（与 get_recordings 相同的筛选条件）
    count_query = "SELECT COUNT(*) FROM recordings WHERE 1=1"
    count_params = []

    if channel_id:
        count_query += " AND channel_id = ?"
        count_params.append(channel_id)

    if user_id:
        count_query += " AND user_id = ?"
        count_params.append(user_id)

    if date:
        count_query += " AND DATE(timestamp) = ?"
        count_params.append(date)

    if min_duration:
        count_query += " AND duration >= ?"
        count_params.append(min_duration)

    if search:
        count_query += " AND (asr_text LIKE ? OR content_normalized LIKE ?)"
        search_pattern = f"%{search}%"
        count_params.append(search_pattern)
        count_params.append(search_pattern)

    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]
    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "recordings": recording_list,
            "total": total,
            "page": page,
            "page_size": page_size
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
