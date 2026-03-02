"""
录音 API - 录音列表、详情、播放
"""
from typing import Optional
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
        search=search,
        limit=page_size,
        offset=offset
    )

    # 转换为字典
    recording_list = []
    for rec in recordings:
        # 处理音频路径 - 从绝对路径中提取相对路径
        audio_path = rec.filepath
        # 查找 "recordings" 在路径中的位置
        idx = audio_path.find("recordings")
        if idx >= 0:
            # 从 "recordings" 开始截取
            audio_path = audio_path[idx:]
            # 转换 Windows 反斜杠为正斜杠（URL 需要正斜杠）
            audio_path = audio_path.replace("\\", "/")
        else:
            # 如果路径中没有 recordings，使用文件名
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

    # 获取总数（简化处理，实际可能需要单独查询）
    total = len(recording_list)

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

    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": recording.id,
            "filename": recording.filename,
            "filepath": recording.filepath,
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
