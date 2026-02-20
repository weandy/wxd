"""数据维护模块 - 数据库操作"""
import sqlite3
import os
from datetime import datetime

# 计算数据库路径（相对于项目根目录）
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
MANAGEMENT_DB_PATH = os.path.join(_project_root, 'data', 'management.db')


def get_mdb():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(MANAGEMENT_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(MANAGEMENT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_tables():
    """初始化数据库表"""
    conn = get_mdb()
    cursor = conn.cursor()

    # SSRC 映射表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ssrc_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ssrc INTEGER UNIQUE NOT NULL,
            nickname TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 纠错规则表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS correction_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type TEXT NOT NULL CHECK(rule_type IN ('letter', 'number', 'word')),
            from_text TEXT NOT NULL,
            to_text TEXT NOT NULL,
            enabled INTEGER DEFAULT 1 CHECK(enabled IN (0, 1)),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(rule_type, from_text)
        )
    ''')

    # 操作日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


# ==================== SSRC 映射操作 ====================

def add_ssrc_mapping(ssrc: int, nickname: str) -> dict:
    """添加 SSRC 映射"""
    conn = get_mdb()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO ssrc_mapping (ssrc, nickname) VALUES (?, ?)",
            (ssrc, nickname)
        )
        conn.commit()
        return {"success": True, "id": cursor.lastrowid}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "SSRC 已存在"}
    finally:
        conn.close()


def get_all_ssrc_mappings() -> list:
    """获取所有映射"""
    conn = get_mdb()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ssrc_mapping ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_ssrc_mapping(id: int, ssrc: int, nickname: str) -> dict:
    """更新映射"""
    conn = get_mdb()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE ssrc_mapping SET ssrc=?, nickname=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (ssrc, nickname, id)
    )
    conn.commit()
    conn.close()
    return {"success": True}


def delete_ssrc_mapping(id: int) -> dict:
    """删除映射"""
    conn = get_mdb()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ssrc_mapping WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"success": True}


# ==================== 纠错规则操作 ====================

def add_correction_rule(rule_type: str, from_text: str, to_text: str) -> dict:
    """添加纠错规则"""
    conn = get_mdb()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO correction_rules (rule_type, from_text, to_text) VALUES (?, ?, ?)",
            (rule_type, from_text, to_text)
        )
        conn.commit()
        return {"success": True, "id": cursor.lastrowid}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "规则已存在"}
    finally:
        conn.close()


def get_all_correction_rules() -> list:
    """获取所有规则"""
    conn = get_mdb()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM correction_rules ORDER BY rule_type, id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_correction_rule(id: int, rule_type: str, from_text: str, to_text: str) -> dict:
    """更新规则"""
    conn = get_mdb()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE correction_rules SET rule_type=?, from_text=?, to_text=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (rule_type, from_text, to_text, id)
    )
    conn.commit()
    conn.close()
    return {"success": True}


def toggle_correction_rule(id: int) -> dict:
    """切换规则启用状态"""
    conn = get_mdb()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE correction_rules SET enabled=CASE WHEN enabled=1 THEN 0 ELSE 1 END, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (id,)
    )
    conn.commit()
    conn.close()
    return {"success": True}


def delete_correction_rule(id: int) -> dict:
    """删除规则"""
    conn = get_mdb()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM correction_rules WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"success": True}


# ==================== 操作日志 ====================

def add_audit_log(username: str, action: str, target: str = None, details: str = None) -> dict:
    """添加操作日志"""
    conn = get_mdb()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO audit_log (username, action, target, details) VALUES (?, ?, ?, ?)",
        (username, action, target, details)
    )
    conn.commit()
    conn.close()
    return {"success": True}


def get_audit_logs(username: str = None, action: str = None, start_date: str = None, end_date: str = None, limit: int = 100) -> list:
    """获取操作日志"""
    conn = get_mdb()
    cursor = conn.cursor()

    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []

    if username:
        query += " AND username = ?"
        params.append(username)
    if action:
        query += " AND action = ?"
        params.append(action)
    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def export_audit_logs_csv(username: str = None, action: str = None, start_date: str = None, end_date: str = None) -> str:
    """导出操作日志为 CSV"""
    import csv
    import io

    logs = get_audit_logs(username, action, start_date, end_date, limit=10000)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['id', 'username', 'action', 'target', 'details', 'created_at'])
    writer.writeheader()
    writer.writerows(logs)

    return output.getvalue()
