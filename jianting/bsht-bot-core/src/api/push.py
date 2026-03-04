"""
推送服务管理 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from datetime import datetime

from src.database import Database


router = APIRouter()


# ===== 请求/响应模型 =====

class ServiceCreate(BaseModel):
    """创建推送服务请求"""
    name: str
    type: str  # wxpusher, bark, telegram, etc.
    url: str
    token: Optional[str] = None
    config: Optional[str] = "{}"
    enabled: Optional[bool] = True


class ServiceUpdate(BaseModel):
    """更新推送服务请求"""
    name: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    token: Optional[str] = None
    config: Optional[str] = None
    enabled: Optional[bool] = None


class UserCreate(BaseModel):
    """创建推送用户请求"""
    service_id: int
    name: str
    user_identifier: str
    keywords: Optional[str] = ""
    enabled: Optional[bool] = True


class UserUpdate(BaseModel):
    """更新推送用户请求"""
    name: Optional[str] = None
    user_identifier: Optional[str] = None
    keywords: Optional[str] = None
    enabled: Optional[bool] = None


class PushTest(BaseModel):
    """测试推送请求"""
    service_id: int
    user_id: Optional[int] = None
    message: str = "这是一条测试消息"


# ===== 依赖项 =====

def get_db():
    """获取数据库实例"""
    return Database()


# ===== API 端点 =====
# 注意：特殊路径必须在参数路径之前定义

@router.get("/push/services/stats")
async def get_push_stats(db: Database = Depends(get_db)):
    """
    获取推送服务统计

    Returns:
        统计数据
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 服务总数
    cursor.execute("SELECT COUNT(*) FROM notify_services")
    total_services = cursor.fetchone()[0]

    # 启用的服务数
    cursor.execute("SELECT COUNT(*) FROM notify_services WHERE enabled = 1")
    enabled_services = cursor.fetchone()[0]

    # 推送用户数
    cursor.execute("SELECT COUNT(*) FROM notify_users")
    total_users = cursor.fetchone()[0]

    # 启用的用户数
    cursor.execute("SELECT COUNT(*) FROM notify_users WHERE enabled = 1")
    enabled_users = cursor.fetchone()[0]

    # 各类型服务数
    cursor.execute("""
        SELECT type, COUNT(*) as count
        FROM notify_services
        GROUP BY type
    """)
    by_type = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "total_services": total_services,
            "enabled_services": enabled_services,
            "disabled_services": total_services - enabled_services,
            "total_users": total_users,
            "enabled_users": enabled_users,
            "by_type": by_type
        }
    }


@router.post("/push/test")
async def test_push(test_data: PushTest, db: Database = Depends(get_db)):
    """
    测试推送功能

    Args:
        test_data: 测试数据

    Returns:
        测试结果
    """
    import sqlite3
    import httpx

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 获取服务配置
    cursor.execute("SELECT * FROM notify_services WHERE id = ?", (test_data.service_id,))
    service_row = cursor.fetchone()
    if not service_row:
        conn.close()
        raise HTTPException(status_code=404, detail="推送服务不存在")

    columns = [desc[0] for desc in cursor.description]
    service = dict(zip(columns, service_row))
    service['enabled'] = bool(service['enabled'])

    # 如果指定了用户，获取用户信息
    target_users = []
    if test_data.user_id:
        cursor.execute("SELECT * FROM notify_users WHERE id = ? AND service_id = ?",
                      (test_data.user_id, test_data.service_id))
        user_row = cursor.fetchone()
        if user_row:
            user_columns = [desc[0] for desc in cursor.description]
            user = dict(zip(user_columns, user_row))
            user['enabled'] = bool(user['enabled'])
            target_users.append(user)
    else:
        # 获取该服务的所有启用用户
        cursor.execute("SELECT * FROM notify_users WHERE service_id = ? AND enabled = 1",
                      (test_data.service_id,))
        rows = cursor.fetchall()
        user_columns = [desc[0] for desc in cursor.description]
        for row in rows:
            user = dict(zip(user_columns, row))
            user['enabled'] = bool(user['enabled'])
            target_users.append(user)

    conn.close()

    # 执行推送
    results = []
    if service['type'] == 'wxpusher':
        # WxPusher 推送
        url = service['url']
        token = service['token']

        for user in target_users:
            try:
                payload = {
                    "token": token,
                    "uid": user['user_identifier'],
                    "title": "BSHT Bot 测试消息",  # 添加标题
                    "content": test_data.message
                }

                with httpx.Client(timeout=10) as client:
                    response = client.post(url, json=payload)
                    result_data = response.json()

                # 判断成功：WxPusher 返回 {"msg":"Successfully sent..."}
                success = ('msg' in result_data and
                          'Successfully' in result_data.get('msg', ''))

                results.append({
                    "user": user['name'],
                    "uid": user['user_identifier'],
                    "success": success,
                    "response": result_data
                })
            except Exception as e:
                results.append({
                    "user": user['name'],
                    "uid": user['user_identifier'],
                    "success": False,
                    "error": str(e)
                })
    else:
        # 其他类型的推送（暂未实现）
        results.append({
            "service_type": service['type'],
            "success": False,
            "error": f"暂不支持 {service['type']} 类型的推送测试"
        })

    return {
        "code": 0,
        "message": "success",
        "data": {
            "service": service['name'],
            "test_message": test_data.message,
            "results": results,
            "total_sent": len(results),
            "success_count": sum(1 for r in results if r.get('success'))
        }
    }


@router.post("/push/services/toggle")
async def toggle_service(service_id: int = Body(...), db: Database = Depends(get_db)):
    """
    切换推送服务启用状态

    Args:
        service_id: 服务ID

    Returns:
        切换结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT enabled FROM notify_services WHERE id = ?", (service_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="推送服务不存在")

    current_status = row[0]
    new_status = 0 if current_status == 1 else 1

    try:
        cursor.execute(
            "UPDATE notify_services SET enabled = ?, updated_at = ? WHERE id = ?",
            (new_status, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), service_id)
        )
        conn.commit()

        return {
            "code": 0,
            "message": "状态切换成功",
            "data": {
                "id": service_id,
                "enabled": bool(new_status)
            }
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"切换失败: {str(e)}")
    finally:
        conn.close()


@router.post("/push/users/toggle")
async def toggle_push_user(user_id: int = Body(...), db: Database = Depends(get_db)):
    """
    切换推送用户启用状态

    Args:
        user_id: 用户ID

    Returns:
        切换结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT enabled FROM notify_users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="推送用户不存在")

    current_status = row[0]
    new_status = 0 if current_status == 1 else 1

    try:
        cursor.execute(
            "UPDATE notify_users SET enabled = ? WHERE id = ?",
            (new_status, user_id)
        )
        conn.commit()

        return {
            "code": 0,
            "message": "状态切换成功",
            "data": {
                "id": user_id,
                "enabled": bool(new_status)
            }
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"切换失败: {str(e)}")
    finally:
        conn.close()


@router.get("/push/services")
async def get_services(
    type: Optional[str] = None,
    enabled: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Database = Depends(get_db)
):
    """
    获取推送服务列表

    Args:
        type: 服务类型筛选
        enabled: 启用状态筛选
        search: 搜索关键词
        page: 页码
        page_size: 每页数量

    Returns:
        服务列表
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    where_conditions = []
    params = []

    if type:
        where_conditions.append("type = ?")
        params.append(type)

    if enabled is not None:
        where_conditions.append("enabled = ?")
        params.append(1 if enabled else 0)

    if search:
        where_conditions.append("(name LIKE ? OR url LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

    # 查询总数
    count_query = f"SELECT COUNT(*) FROM notify_services WHERE {where_clause}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    # 查询列表
    offset = (page - 1) * page_size
    query = f"""
        SELECT s.*,
               (SELECT COUNT(*) FROM notify_users WHERE service_id = s.id) as user_count
        FROM notify_services s
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    cursor.execute(query, params)

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    services = []
    for row in rows:
        service = dict(zip(columns, row))
        service['enabled'] = bool(service['enabled'])
        services.append(service)

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "services": services,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    }


@router.post("/push/services")
async def create_service(service: ServiceCreate, db: Database = Depends(get_db)):
    """
    创建推送服务

    Args:
        service: 服务数据

    Returns:
        创建的服务ID
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        cursor.execute("""
            INSERT INTO notify_services (name, type, url, token, config, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            service.name,
            service.type,
            service.url,
            service.token,
            service.config,
            1 if service.enabled else 0,
            now,
            now
        ))

        service_id = cursor.lastrowid
        conn.commit()

        return {
            "code": 0,
            "message": "创建成功",
            "data": {"id": service_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")
    finally:
        conn.close()


@router.get("/push/services/{service_id}")
async def get_service(service_id: int, db: Database = Depends(get_db)):
    """
    获取单个推送服务详情

    Args:
        service_id: 服务ID

    Returns:
        服务详情
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM notify_services WHERE id = ?", (service_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="推送服务不存在")

    columns = [desc[0] for desc in cursor.description]
    service = dict(zip(columns, row))
    service['enabled'] = bool(service['enabled'])

    cursor.execute("SELECT COUNT(*) FROM notify_users WHERE service_id = ?", (service_id,))
    service['user_count'] = cursor.fetchone()[0]

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": service
    }


@router.put("/push/services/{service_id}")
async def update_service(service_id: int, service: ServiceUpdate, db: Database = Depends(get_db)):
    """
    更新推送服务

    Args:
        service_id: 服务ID
        service: 更新数据

    Returns:
        更新结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM notify_services WHERE id = ?", (service_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="推送服务不存在")

    update_fields = []
    params = []

    if service.name is not None:
        update_fields.append("name = ?")
        params.append(service.name)

    if service.type is not None:
        update_fields.append("type = ?")
        params.append(service.type)

    if service.url is not None:
        update_fields.append("url = ?")
        params.append(service.url)

    if service.token is not None:
        update_fields.append("token = ?")
        params.append(service.token)

    if service.config is not None:
        update_fields.append("config = ?")
        params.append(service.config)

    if service.enabled is not None:
        update_fields.append("enabled = ?")
        params.append(1 if service.enabled else 0)

    update_fields.append("updated_at = ?")
    params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    params.append(service_id)

    try:
        query = f"UPDATE notify_services SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()

        return {
            "code": 0,
            "message": "更新成功",
            "data": {"id": service_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")
    finally:
        conn.close()


@router.delete("/push/services/{service_id}")
async def delete_service(service_id: int, db: Database = Depends(get_db)):
    """
    删除推送服务（同时删除关联的用户）

    Args:
        service_id: 服务ID

    Returns:
        删除结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM notify_services WHERE id = ?", (service_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="推送服务不存在")

    try:
        # 先删除关联的用户
        cursor.execute("DELETE FROM notify_users WHERE service_id = ?", (service_id,))
        # 再删除服务
        cursor.execute("DELETE FROM notify_services WHERE id = ?", (service_id,))

        conn.commit()

        return {
            "code": 0,
            "message": "删除成功",
            "data": {"id": service_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
    finally:
        conn.close()


@router.get("/push/users")
async def get_push_users(
    service_id: Optional[int] = None,
    enabled: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Database = Depends(get_db)
):
    """
    获取推送用户列表

    Args:
        service_id: 服务ID筛选
        enabled: 启用状态筛选
        search: 搜索关键词
        page: 页码
        page_size: 每页数量

    Returns:
        用户列表
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    where_conditions = []
    params = []

    if service_id:
        where_conditions.append("u.service_id = ?")
        params.append(service_id)

    if enabled is not None:
        where_conditions.append("u.enabled = ?")
        params.append(1 if enabled else 0)

    if search:
        where_conditions.append("(u.name LIKE ? OR u.user_identifier LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

    # 查询总数
    count_query = f"SELECT COUNT(*) FROM notify_users u WHERE {where_clause}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    # 查询列表
    offset = (page - 1) * page_size
    query = f"""
        SELECT u.*, s.name as service_name, s.type as service_type
        FROM notify_users u
        LEFT JOIN notify_services s ON u.service_id = s.id
        WHERE {where_clause}
        ORDER BY u.service_id, u.id
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    cursor.execute(query, params)

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    users = []
    for row in rows:
        user = dict(zip(columns, row))
        user['enabled'] = bool(user['enabled'])
        users.append(user)

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "users": users,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    }


@router.post("/push/users")
async def create_push_user(user: UserCreate, db: Database = Depends(get_db)):
    """
    创建推送用户

    Args:
        user: 用户数据

    Returns:
        创建的用户ID
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 检查服务是否存在
    cursor.execute("SELECT id FROM notify_services WHERE id = ?", (user.service_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="推送服务不存在")

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        cursor.execute("""
            INSERT INTO notify_users (service_id, name, user_identifier, keywords, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user.service_id,
            user.name,
            user.user_identifier,
            user.keywords,
            1 if user.enabled else 0,
            now
        ))

        user_id = cursor.lastrowid
        conn.commit()

        return {
            "code": 0,
            "message": "创建成功",
            "data": {"id": user_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")
    finally:
        conn.close()


@router.get("/push/users/{user_id}")
async def get_push_user(user_id: int, db: Database = Depends(get_db)):
    """
    获取单个推送用户详情

    Args:
        user_id: 用户ID

    Returns:
        用户详情
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.*, s.name as service_name, s.type as service_type
        FROM notify_users u
        LEFT JOIN notify_services s ON u.service_id = s.id
        WHERE u.id = ?
    """, (user_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="推送用户不存在")

    columns = [desc[0] for desc in cursor.description]
    user = dict(zip(columns, row))
    user['enabled'] = bool(user['enabled'])

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": user
    }


@router.put("/push/users/{user_id}")
async def update_push_user(user_id: int, user: UserUpdate, db: Database = Depends(get_db)):
    """
    更新推送用户

    Args:
        user_id: 用户ID
        user: 更新数据

    Returns:
        更新结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM notify_users WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="推送用户不存在")

    update_fields = []
    params = []

    if user.name is not None:
        update_fields.append("name = ?")
        params.append(user.name)

    if user.user_identifier is not None:
        update_fields.append("user_identifier = ?")
        params.append(user.user_identifier)

    if user.keywords is not None:
        update_fields.append("keywords = ?")
        params.append(user.keywords)

    if user.enabled is not None:
        update_fields.append("enabled = ?")
        params.append(1 if user.enabled else 0)

    params.append(user_id)

    try:
        query = f"UPDATE notify_users SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()

        return {
            "code": 0,
            "message": "更新成功",
            "data": {"id": user_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")
    finally:
        conn.close()


@router.delete("/push/users/{user_id}")
async def delete_push_user(user_id: int, db: Database = Depends(get_db)):
    """
    删除推送用户

    Args:
        user_id: 用户ID

    Returns:
        删除结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM notify_users WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="推送用户不存在")

    try:
        cursor.execute("DELETE FROM notify_users WHERE id = ?", (user_id,))
        conn.commit()

        return {
            "code": 0,
            "message": "删除成功",
            "data": {"id": user_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
    finally:
        conn.close()
