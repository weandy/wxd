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
