"""
广播任务管理 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from datetime import datetime

from src.database import Database


router = APIRouter()


# ===== 请求/响应模型 =====

class BroadcastTaskCreate(BaseModel):
    """创建广播任务请求"""
    name: str
    task_type: str  # audio, tts
    trigger_type: str  # manual, schedule, keyword
    trigger_config: Optional[str] = "{}"
    content_type: str  # audio_file, text
    audio_file_id: Optional[int] = None
    tts_text: Optional[str] = None
    tts_config: Optional[str] = "{}"
    is_enabled: Optional[bool] = True


class BroadcastTaskUpdate(BaseModel):
    """更新广播任务请求"""
    name: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[str] = None
    audio_file_id: Optional[int] = None
    tts_text: Optional[str] = None
    tts_config: Optional[str] = None
    is_enabled: Optional[bool] = None


class TaskExecute(BaseModel):
    """执行任务请求"""
    task_id: int
    target_channels: Optional[list[int]] = None


# ===== 依赖项 =====

def get_db():
    """获取数据库实例"""
    return Database()


# ===== API 端点 =====

@router.get("/broadcast/stats")
async def get_broadcast_stats(db: Database = Depends(get_db)):
    """
    获取广播任务统计

    Returns:
        统计数据
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 总任务数
    cursor.execute("SELECT COUNT(*) FROM broadcast_tasks")
    total = cursor.fetchone()[0]

    # 启用的任务数
    cursor.execute("SELECT COUNT(*) FROM broadcast_tasks WHERE is_enabled = 1")
    enabled = cursor.fetchone()[0]

    # 各类型任务数
    cursor.execute("""
        SELECT task_type, COUNT(*) as count
        FROM broadcast_tasks
        GROUP BY task_type
    """)
    by_type = {row[0]: row[1] for row in cursor.fetchall()}

    # 各触发类型任务数
    cursor.execute("""
        SELECT trigger_type, COUNT(*) as count
        FROM broadcast_tasks
        GROUP BY trigger_type
    """)
    by_trigger = {row[0]: row[1] for row in cursor.fetchall()}

    # 总执行次数
    cursor.execute("SELECT SUM(execution_count) FROM broadcast_tasks")
    total_executions = cursor.fetchone()[0] or 0

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "by_type": by_type,
            "by_trigger": by_trigger,
            "total_executions": total_executions
        }
    }


@router.post("/broadcast/execute")
async def execute_broadcast_task_api(task_data: TaskExecute, db: Database = Depends(get_db)):
    """
    执行广播任务

    Args:
        task_data: 任务数据

    Returns:
        执行结果
    """
    import sqlite3
    from src.bot_communicator import execute_broadcast_task

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 获取任务信息
    cursor.execute("SELECT * FROM broadcast_tasks WHERE id = ?", (task_data.task_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="任务不存在")

    columns = [desc[0] for desc in cursor.description]
    task = dict(zip(columns, row))
    task['is_enabled'] = bool(task['is_enabled'])

    if not task['is_enabled']:
        conn.close()
        raise HTTPException(status_code=400, detail="任务已禁用")

    # 准备执行参数
    audio_filepath = None
    if task['task_type'] == 'audio' and task['audio_file_id']:
        # 获取音频文件路径
        cursor.execute("SELECT filepath FROM audio_library WHERE id = ?", (task['audio_file_id'],))
        audio_row = cursor.fetchone()
        if audio_row:
            audio_filepath = audio_row[0]

    # 执行广播任务
    try:
        broadcast_result = await execute_broadcast_task(
            task_type=task['task_type'],
            audio_filepath=audio_filepath,
            tts_text=task.get('tts_text'),
            channel_id=None  # 使用默认频道
        )

        execution_result = {
            "task_id": task['id'],
            "task_name": task['name'],
            "task_type": task['task_type'],
            "executed_at": datetime.now().isoformat(),
            "success": broadcast_result.get('success', False),
            "message": broadcast_result.get('message', '执行完成'),
            "target_channels": task_data.target_channels or [],
            "details": broadcast_result
        }

        # 更新执行次数和时间
        cursor.execute(
            "UPDATE broadcast_tasks SET last_executed = ?, execution_count = execution_count + 1 WHERE id = ?",
            (datetime.now().isoformat(), task['id'])
        )
        conn.commit()

        conn.close()

        return {
            "code": 0,
            "message": "success",
            "data": execution_result
        }

    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.post("/broadcast/toggle")
async def toggle_broadcast_task(task_id: int = Body(..., embed=True), db: Database = Depends(get_db)):
    """
    切换广播任务启用状态

    Args:
        task_id: 任务ID

    Returns:
        切换结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT is_enabled FROM broadcast_tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="任务不存在")

    current_status = row[0]
    new_status = 0 if current_status == 1 else 1

    try:
        cursor.execute(
            "UPDATE broadcast_tasks SET is_enabled = ? WHERE id = ?",
            (new_status, task_id)
        )
        conn.commit()

        return {
            "code": 0,
            "message": "状态切换成功",
            "data": {
                "id": task_id,
                "is_enabled": bool(new_status)
            }
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"切换失败: {str(e)}")
    finally:
        conn.close()


@router.get("/broadcast/tasks")
async def get_broadcast_tasks(
    task_type: Optional[str] = None,
    trigger_type: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Database = Depends(get_db)
):
    """
    获取广播任务列表

    Args:
        task_type: 任务类型筛选
        trigger_type: 触发类型筛选
        is_enabled: 启用状态筛选
        search: 搜索关键词
        page: 页码
        page_size: 每页数量

    Returns:
        任务列表
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 构建查询条件
    where_conditions = []
    params = []

    if task_type:
        where_conditions.append("task_type = ?")
        params.append(task_type)

    if trigger_type:
        where_conditions.append("trigger_type = ?")
        params.append(trigger_type)

    if is_enabled is not None:
        where_conditions.append("is_enabled = ?")
        params.append(1 if is_enabled else 0)

    if search:
        where_conditions.append("(name LIKE ? OR tts_text LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

    # 查询总数
    count_query = f"SELECT COUNT(*) FROM broadcast_tasks WHERE {where_clause}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    # 查询列表
    offset = (page - 1) * page_size
    query = f"""
        SELECT * FROM broadcast_tasks
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    cursor.execute(query, params)

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    tasks = []
    for row in rows:
        task = dict(zip(columns, row))
        task['is_enabled'] = bool(task['is_enabled'])
        tasks.append(task)

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "tasks": tasks,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    }


@router.post("/broadcast/tasks")
async def create_broadcast_task(task: BroadcastTaskCreate, db: Database = Depends(get_db)):
    """
    创建广播任务

    Args:
        task: 任务数据

    Returns:
        创建的任务ID
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # 验证任务类型和内容类型匹配
    if task.task_type == "audio" and task.content_type != "audio_file":
        conn.close()
        raise HTTPException(status_code=400, detail="音频任务必须使用audio_file内容类型")

    if task.task_type == "tts" and task.content_type != "text":
        conn.close()
        raise HTTPException(status_code=400, detail="TTS任务必须使用text内容类型")

    try:
        cursor.execute("""
            INSERT INTO broadcast_tasks (name, task_type, trigger_type, trigger_config,
                                        content_type, audio_file_id, tts_text, tts_config,
                                        is_enabled, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.name,
            task.task_type,
            task.trigger_type,
            task.trigger_config,
            task.content_type,
            task.audio_file_id,
            task.tts_text,
            task.tts_config,
            1 if task.is_enabled else 0,
            1,  # 默认创建者为ID=1的用户
            now
        ))

        task_id = cursor.lastrowid
        conn.commit()

        return {
            "code": 0,
            "message": "创建成功",
            "data": {"id": task_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")
    finally:
        conn.close()


@router.get("/broadcast/tasks/{task_id}")
async def get_broadcast_task(task_id: int, db: Database = Depends(get_db)):
    """
    获取单个广播任务详情

    Args:
        task_id: 任务ID

    Returns:
        任务详情
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM broadcast_tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="任务不存在")

    columns = [desc[0] for desc in cursor.description]
    task = dict(zip(columns, row))
    task['is_enabled'] = bool(task['is_enabled'])

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": task
    }


@router.put("/broadcast/tasks/{task_id}")
async def update_broadcast_task(task_id: int, task: BroadcastTaskUpdate, db: Database = Depends(get_db)):
    """
    更新广播任务

    Args:
        task_id: 任务ID
        task: 更新数据

    Returns:
        更新结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM broadcast_tasks WHERE id = ?", (task_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="任务不存在")

    # 构建更新语句
    update_fields = []
    params = []

    if task.name is not None:
        update_fields.append("name = ?")
        params.append(task.name)

    if task.trigger_type is not None:
        update_fields.append("trigger_type = ?")
        params.append(task.trigger_type)

    if task.trigger_config is not None:
        update_fields.append("trigger_config = ?")
        params.append(task.trigger_config)

    if task.audio_file_id is not None:
        update_fields.append("audio_file_id = ?")
        params.append(task.audio_file_id)

    if task.tts_text is not None:
        update_fields.append("tts_text = ?")
        params.append(task.tts_text)

    if task.tts_config is not None:
        update_fields.append("tts_config = ?")
        params.append(task.tts_config)

    if task.is_enabled is not None:
        update_fields.append("is_enabled = ?")
        params.append(1 if task.is_enabled else 0)

    params.append(task_id)

    try:
        query = f"UPDATE broadcast_tasks SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()

        return {
            "code": 0,
            "message": "更新成功",
            "data": {"id": task_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")
    finally:
        conn.close()


@router.delete("/broadcast/tasks/{task_id}")
async def delete_broadcast_task(task_id: int, db: Database = Depends(get_db)):
    """
    删除广播任务

    Args:
        task_id: 任务ID

    Returns:
        删除结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM broadcast_tasks WHERE id = ?", (task_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="任务不存在")

    try:
        cursor.execute("DELETE FROM broadcast_tasks WHERE id = ?", (task_id,))
        conn.commit()

        return {
            "code": 0,
            "message": "删除成功",
            "data": {"id": task_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
    finally:
        conn.close()


@router.post("/broadcast/tasks/batch-delete")
async def batch_delete_broadcast_tasks(task_ids: list[int], db: Database = Depends(get_db)):
    """
    批量删除广播任务

    Args:
        task_ids: 任务ID列表

    Returns:
        删除结果
    """
    import sqlite3

    if not task_ids:
        raise HTTPException(status_code=400, detail="任务ID列表不能为空")

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    try:
        placeholders = ','.join(['?' for _ in task_ids])
        cursor.execute(f"DELETE FROM broadcast_tasks WHERE id IN ({placeholders})", task_ids)
        deleted_count = cursor.rowcount
        conn.commit()

        return {
            "code": 0,
            "message": f"成功删除 {deleted_count} 个任务",
            "data": {"deleted_count": deleted_count}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")
    finally:
        conn.close()
