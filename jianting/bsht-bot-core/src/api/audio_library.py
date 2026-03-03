"""
音频库管理 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime

from src.database import Database


router = APIRouter()


# ===== 请求/响应模型 =====

class AudioLibraryCreate(BaseModel):
    """创建音频库条目请求"""
    filename: str
    filepath: str
    source_type: str  # recording, upload, tts, etc.
    description: Optional[str] = None
    duration: Optional[float] = None
    file_size: Optional[int] = None
    metadata: Optional[str] = "{}"


class AudioLibraryUpdate(BaseModel):
    """更新音频库条目请求"""
    filename: Optional[str] = None
    filepath: Optional[str] = None
    source_type: Optional[str] = None
    description: Optional[str] = None
    duration: Optional[float] = None
    file_size: Optional[int] = None
    metadata: Optional[str] = None


# ===== 依赖项 =====

def get_db():
    """获取数据库实例"""
    return Database()


# ===== API 端点 =====

@router.get("/audio-library/stats")
async def get_audio_library_stats(db: Database = Depends(get_db)):
    """
    获取音频库统计

    Returns:
        统计数据
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 总音频数
    cursor.execute("SELECT COUNT(*) FROM audio_library")
    total = cursor.fetchone()[0]

    # 总时长（秒）
    cursor.execute("SELECT SUM(duration) FROM audio_library")
    total_duration = cursor.fetchone()[0] or 0

    # 总大小（字节）
    cursor.execute("SELECT SUM(file_size) FROM audio_library")
    total_size = cursor.fetchone()[0] or 0

    # 按来源类型分组统计
    cursor.execute("""
        SELECT source_type, COUNT(*) as count, SUM(duration) as total_duration
        FROM audio_library
        GROUP BY source_type
    """)
    by_type = {row[0]: {"count": row[1], "duration": row[2] or 0} for row in cursor.fetchall()}

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "total": total,
            "total_duration": total_duration,
            "total_size": total_size,
            "by_type": by_type
        }
    }


@router.get("/audio-library")
async def get_audio_library(
    source_type: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Database = Depends(get_db)
):
    """
    获取音频库列表

    Args:
        source_type: 来源类型筛选
        search: 搜索关键词（文件名、描述）
        page: 页码
        page_size: 每页数量

    Returns:
        音频列表
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 构建查询条件
    where_conditions = []
    params = []

    if source_type:
        where_conditions.append("source_type = ?")
        params.append(source_type)

    if search:
        where_conditions.append("(filename LIKE ? OR description LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

    # 查询总数
    count_query = f"SELECT COUNT(*) FROM audio_library WHERE {where_clause}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    # 查询列表
    offset = (page - 1) * page_size
    query = f"""
        SELECT * FROM audio_library
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    cursor.execute(query, params)

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    audio_items = []
    for row in rows:
        item = dict(zip(columns, row))
        audio_items.append(item)

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": audio_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    }


@router.post("/audio-library")
async def create_audio_item(item: AudioLibraryCreate, db: Database = Depends(get_db)):
    """
    创建音频库条目

    Args:
        item: 音频数据

    Returns:
        创建的音频ID
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    try:
        cursor.execute("""
            INSERT INTO audio_library (filename, filepath, source_type, description, duration, file_size, metadata, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.filename,
            item.filepath,
            item.source_type,
            item.description,
            item.duration,
            item.file_size,
            item.metadata,
            1,  # 默认创建者为ID=1的用户
            now
        ))

        item_id = cursor.lastrowid
        conn.commit()

        return {
            "code": 0,
            "message": "创建成功",
            "data": {"id": item_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")
    finally:
        conn.close()


@router.get("/audio-library/{item_id}")
async def get_audio_item(item_id: int, db: Database = Depends(get_db)):
    """
    获取单个音频库条目详情

    Args:
        item_id: 音频ID

    Returns:
        音频详情
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM audio_library WHERE id = ?", (item_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="音频不存在")

    columns = [desc[0] for desc in cursor.description]
    item = dict(zip(columns, row))

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": item
    }


@router.put("/audio-library/{item_id}")
async def update_audio_item(item_id: int, item: AudioLibraryUpdate, db: Database = Depends(get_db)):
    """
    更新音频库条目

    Args:
        item_id: 音频ID
        item: 更新数据

    Returns:
        更新结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM audio_library WHERE id = ?", (item_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="音频不存在")

    # 构建更新语句
    update_fields = []
    params = []

    if item.filename is not None:
        update_fields.append("filename = ?")
        params.append(item.filename)

    if item.filepath is not None:
        update_fields.append("filepath = ?")
        params.append(item.filepath)

    if item.source_type is not None:
        update_fields.append("source_type = ?")
        params.append(item.source_type)

    if item.description is not None:
        update_fields.append("description = ?")
        params.append(item.description)

    if item.duration is not None:
        update_fields.append("duration = ?")
        params.append(item.duration)

    if item.file_size is not None:
        update_fields.append("file_size = ?")
        params.append(item.file_size)

    if item.metadata is not None:
        update_fields.append("metadata = ?")
        params.append(item.metadata)

    params.append(item_id)

    try:
        query = f"UPDATE audio_library SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()

        return {
            "code": 0,
            "message": "更新成功",
            "data": {"id": item_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")
    finally:
        conn.close()


@router.delete("/audio-library/{item_id}")
async def delete_audio_item(item_id: int, db: Database = Depends(get_db)):
    """
    删除音频库条目

    Args:
        item_id: 音频ID

    Returns:
        删除结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM audio_library WHERE id = ?", (item_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="音频不存在")

    try:
        cursor.execute("DELETE FROM audio_library WHERE id = ?", (item_id,))
        conn.commit()

        return {
            "code": 0,
            "message": "删除成功",
            "data": {"id": item_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
    finally:
        conn.close()


@router.post("/audio-library/batch-delete")
async def batch_delete_audio_items(item_ids: list[int], db: Database = Depends(get_db)):
    """
    批量删除音频库条目

    Args:
        item_ids: 音频ID列表

    Returns:
        删除结果
    """
    import sqlite3

    if not item_ids:
        raise HTTPException(status_code=400, detail="音频ID列表不能为空")

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    try:
        placeholders = ','.join(['?' for _ in item_ids])
        cursor.execute(f"DELETE FROM audio_library WHERE id IN ({placeholders})", item_ids)
        deleted_count = cursor.rowcount
        conn.commit()

        return {
            "code": 0,
            "message": f"成功删除 {deleted_count} 条音频",
            "data": {"deleted_count": deleted_count}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")
    finally:
        conn.close()
