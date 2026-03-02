"""
纠错规则管理 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime

from src.database import Database


router = APIRouter()


# ===== 请求/响应模型 =====

class RuleCreate(BaseModel):
    """创建规则请求"""
    name: str
    rule_type: str  # replace, regex, signal_type
    pattern: str
    replacement: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = "general"
    priority: Optional[int] = 0
    is_enabled: Optional[bool] = True


class RuleUpdate(BaseModel):
    """更新规则请求"""
    name: Optional[str] = None
    rule_type: Optional[str] = None
    pattern: Optional[str] = None
    replacement: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[int] = None
    is_enabled: Optional[bool] = None


class RuleTest(BaseModel):
    """测试规则请求"""
    text: str
    rule_ids: Optional[list[int]] = None  # 指定测试的规则ID列表，为空则测试所有启用的规则


# ===== 依赖项 =====

def get_db():
    """获取数据库实例"""
    return Database()


# ===== API 端点 =====
# 注意：特殊路径必须在参数路径之前定义，否则会被参数路径匹配

@router.get("/rules/stats")
async def get_rule_stats(db: Database = Depends(get_db)):
    """
    获取规则统计信息

    Returns:
        统计数据
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 总规则数
    cursor.execute("SELECT COUNT(*) FROM correction_rules")
    total = cursor.fetchone()[0]

    # 启用的规则数
    cursor.execute("SELECT COUNT(*) FROM correction_rules WHERE is_enabled = 1")
    enabled = cursor.fetchone()[0]

    # 各类型规则数
    cursor.execute("""
        SELECT rule_type, COUNT(*) as count
        FROM correction_rules
        GROUP BY rule_type
    """)
    by_type = {row[0]: row[1] for row in cursor.fetchall()}

    # 各分类规则数
    cursor.execute("""
        SELECT category, COUNT(*) as count
        FROM correction_rules
        WHERE category IS NOT NULL
        GROUP BY category
    """)
    by_category = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "by_type": by_type,
            "by_category": by_category
        }
    }


@router.get("/rules/categories")
async def get_rule_categories(db: Database = Depends(get_db)):
    """
    获取规则分类列表

    Returns:
        分类列表
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT category
        FROM correction_rules
        WHERE category IS NOT NULL AND category != ''
        ORDER BY category
    """)

    categories = [row[0] for row in cursor.fetchall()]
    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "categories": categories
        }
    }


@router.post("/rules/test")
async def test_rule(test_data: RuleTest, db: Database = Depends(get_db)):
    """
    测试规则应用效果

    Args:
        test_data: 测试数据（文本和可选的规则ID列表）

    Returns:
        测试结果（原始文本、处理后文本、应用的规则）
    """
    import sqlite3
    import re

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 获取要测试的规则
    if test_data.rule_ids:
        placeholders = ','.join(['?' for _ in test_data.rule_ids])
        cursor.execute(f"""
            SELECT * FROM correction_rules
            WHERE id IN ({placeholders}) AND is_enabled = 1
            ORDER BY priority DESC
        """, test_data.rule_ids)
    else:
        cursor.execute("""
            SELECT * FROM correction_rules
            WHERE is_enabled = 1
            ORDER BY priority DESC
        """)

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    rules = []
    for row in rows:
        rule = dict(zip(columns, row))
        rule['is_enabled'] = bool(rule['is_enabled'])
        rules.append(rule)

    conn.close()

    # 应用规则
    result_text = test_data.text
    applied_rules = []

    for rule in rules:
        if rule['rule_type'] == 'replace':
            # 简单替换
            if rule['pattern'] in result_text:
                result_text = result_text.replace(rule['pattern'], rule['replacement'] or '')
                applied_rules.append({
                    'id': rule['id'],
                    'name': rule['name'],
                    'type': 'replace',
                    'pattern': rule['pattern'],
                    'replacement': rule['replacement']
                })

        elif rule['rule_type'] == 'regex':
            # 正则表达式替换
            try:
                pattern = re.compile(rule['pattern'])
                matches = pattern.findall(result_text)
                if matches:
                    result_text = pattern.sub(rule['replacement'] or '', result_text)
                    applied_rules.append({
                        'id': rule['id'],
                        'name': rule['name'],
                        'type': 'regex',
                        'pattern': rule['pattern'],
                        'replacement': rule['replacement'],
                        'matches': matches
                    })
            except re.error as e:
                applied_rules.append({
                    'id': rule['id'],
                    'name': rule['name'],
                    'type': 'regex',
                    'error': f"正则表达式错误: {str(e)}"
                })

    return {
        "code": 0,
        "message": "success",
        "data": {
            "original_text": test_data.text,
            "result_text": result_text,
            "applied_rules": applied_rules,
            "applied_count": len([r for r in applied_rules if 'error' not in r])
        }
    }


@router.post("/rules/toggle")
async def toggle_rule(rule_id: int, db: Database = Depends(get_db)):
    """
    切换规则启用状态

    Args:
        rule_id: 规则ID

    Returns:
        切换结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 检查规则是否存在并获取当前状态
    cursor.execute("SELECT is_enabled FROM correction_rules WHERE id = ?", (rule_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="规则不存在")

    current_status = row[0]
    new_status = 0 if current_status == 1 else 1

    try:
        cursor.execute(
            "UPDATE correction_rules SET is_enabled = ?, updated_at = ? WHERE id = ?",
            (new_status, datetime.now().isoformat(), rule_id)
        )
        conn.commit()

        return {
            "code": 0,
            "message": "状态切换成功",
            "data": {
                "id": rule_id,
                "is_enabled": bool(new_status)
            }
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"切换失败: {str(e)}")
    finally:
        conn.close()


@router.post("/rules/batch-delete")
async def batch_delete_rules(rule_ids: list[int], db: Database = Depends(get_db)):
    """
    批量删除规则

    Args:
        rule_ids: 规则ID列表

    Returns:
        删除结果
    """
    import sqlite3

    if not rule_ids:
        raise HTTPException(status_code=400, detail="规则ID列表不能为空")

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    try:
        placeholders = ','.join(['?' for _ in rule_ids])
        cursor.execute(f"DELETE FROM correction_rules WHERE id IN ({placeholders})", rule_ids)
        deleted_count = cursor.rowcount
        conn.commit()

        return {
            "code": 0,
            "message": f"成功删除 {deleted_count} 条规则",
            "data": {"deleted_count": deleted_count}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")
    finally:
        conn.close()


@router.get("/rules")
async def get_rules(
    rule_type: Optional[str] = None,
    category: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Database = Depends(get_db)
):
    """
    获取规则列表

    Args:
        rule_type: 规则类型筛选
        category: 分类筛选
        is_enabled: 启用状态筛选
        search: 搜索关键词（名称、模式、描述）
        page: 页码
        page_size: 每页数量

    Returns:
        规则列表
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 构建查询条件
    where_conditions = []
    params = []

    if rule_type:
        where_conditions.append("rule_type = ?")
        params.append(rule_type)

    if category:
        where_conditions.append("category = ?")
        params.append(category)

    if is_enabled is not None:
        where_conditions.append("is_enabled = ?")
        params.append(1 if is_enabled else 0)

    if search:
        where_conditions.append("(name LIKE ? OR pattern LIKE ? OR description LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

    # 查询总数
    count_query = f"SELECT COUNT(*) FROM correction_rules WHERE {where_clause}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    # 查询列表
    offset = (page - 1) * page_size
    query = f"""
        SELECT * FROM correction_rules
        WHERE {where_clause}
        ORDER BY priority DESC, created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    cursor.execute(query, params)

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    rules = []
    for row in rows:
        rule = dict(zip(columns, row))
        rule['is_enabled'] = bool(rule['is_enabled'])
        rules.append(rule)

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "rules": rules,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    }


@router.post("/rules")
async def create_rule(rule: RuleCreate, db: Database = Depends(get_db)):
    """
    创建新规则

    Args:
        rule: 规则数据

    Returns:
        创建的规则ID
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    try:
        cursor.execute("""
            INSERT INTO correction_rules
            (name, rule_type, pattern, replacement, description, category, priority, is_enabled, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rule.name,
            rule.rule_type,
            rule.pattern,
            rule.replacement,
            rule.description,
            rule.category,
            rule.priority,
            1 if rule.is_enabled else 0,
            1,  # 默认创建者为ID=1的用户
            now
        ))

        rule_id = cursor.lastrowid
        conn.commit()

        return {
            "code": 0,
            "message": "创建成功",
            "data": {"id": rule_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")
    finally:
        conn.close()


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: int, db: Database = Depends(get_db)):
    """
    获取单个规则详情

    Args:
        rule_id: 规则ID

    Returns:
        规则详情
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM correction_rules WHERE id = ?", (rule_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="规则不存在")

    columns = [desc[0] for desc in cursor.description]
    rule = dict(zip(columns, row))
    rule['is_enabled'] = bool(rule['is_enabled'])

    conn.close()

    return {
        "code": 0,
        "message": "success",
        "data": rule
    }


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, rule: RuleUpdate, db: Database = Depends(get_db)):
    """
    更新规则

    Args:
        rule_id: 规则ID
        rule: 更新数据

    Returns:
        更新结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 检查规则是否存在
    cursor.execute("SELECT id FROM correction_rules WHERE id = ?", (rule_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="规则不存在")

    # 构建更新语句
    update_fields = []
    params = []

    if rule.name is not None:
        update_fields.append("name = ?")
        params.append(rule.name)

    if rule.rule_type is not None:
        update_fields.append("rule_type = ?")
        params.append(rule.rule_type)

    if rule.pattern is not None:
        update_fields.append("pattern = ?")
        params.append(rule.pattern)

    if rule.replacement is not None:
        update_fields.append("replacement = ?")
        params.append(rule.replacement)

    if rule.description is not None:
        update_fields.append("description = ?")
        params.append(rule.description)

    if rule.category is not None:
        update_fields.append("category = ?")
        params.append(rule.category)

    if rule.priority is not None:
        update_fields.append("priority = ?")
        params.append(rule.priority)

    if rule.is_enabled is not None:
        update_fields.append("is_enabled = ?")
        params.append(1 if rule.is_enabled else 0)

    update_fields.append("updated_at = ?")
    params.append(datetime.now().isoformat())

    params.append(rule_id)

    try:
        query = f"UPDATE correction_rules SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()

        return {
            "code": 0,
            "message": "更新成功",
            "data": {"id": rule_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")
    finally:
        conn.close()


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, db: Database = Depends(get_db)):
    """
    删除规则

    Args:
        rule_id: 规则ID

    Returns:
        删除结果
    """
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 检查规则是否存在
    cursor.execute("SELECT id FROM correction_rules WHERE id = ?", (rule_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="规则不存在")

    try:
        cursor.execute("DELETE FROM correction_rules WHERE id = ?", (rule_id,))
        conn.commit()

        return {
            "code": 0,
            "message": "删除成功",
            "data": {"id": rule_id}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
    finally:
        conn.close()
