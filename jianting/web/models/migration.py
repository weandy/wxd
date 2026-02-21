"""数据库迁移脚本 - 创建 Web 管理端所需的新表"""

import sqlite3
import os


def migrate(db_path=None):
    """执行数据库迁移"""
    if db_path is None:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'data', 'records.db'
        )

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # users 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'observer',
            can_listen_recordings BOOLEAN DEFAULT 0,
            can_transmit BOOLEAN DEFAULT 0,
            avatar TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            last_active_at TIMESTAMP,
            must_change_password BOOLEAN DEFAULT 0
        )
    """)

    # channels 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            name TEXT,
            passcode INTEGER DEFAULT 0,
            auto_join BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # config 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT,
            category TEXT,
            description TEXT,
            updated_at TIMESTAMP
        )
    """)

    # config_history 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by INTEGER,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # recordings 表 (Bot 创建录音数据, Web 端读取展示)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER,
            user_id INTEGER,
            user_name TEXT,
            filepath TEXT,
            duration REAL DEFAULT 0,
            timestamp TEXT,
            asr_text TEXT,
            content_normalized TEXT,
            recognized BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # audio_library 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audio_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filename TEXT NOT NULL DEFAULT '',
            filepath TEXT NOT NULL,
            duration REAL DEFAULT 0,
            file_size INTEGER DEFAULT 0,
            use_count INTEGER DEFAULT 0,
            uploaded_by TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # scheduled_tasks 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            audio_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            trigger_type TEXT NOT NULL DEFAULT 'fixed',
            schedule_config TEXT DEFAULT '{}',
            time_window_start TEXT,
            time_window_end TEXT,
            enabled BOOLEAN DEFAULT 1,
            last_run_at TIMESTAMP,
            next_run_at TIMESTAMP,
            created_by TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # scheduled_task_logs 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_task_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # notify_services 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notify_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            url TEXT,
            token TEXT,
            config TEXT,
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    # notify_users 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notify_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            user_identifier TEXT NOT NULL,
            keywords TEXT,
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # bot_commands 表 (进程间通信)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT NOT NULL,
            params TEXT,
            created_by INTEGER,
            status TEXT DEFAULT 'pending',
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
    """)

    # bot_status 表 (进程间通信)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_status (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # login_attempts 表 (登录限流)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            username TEXT,
            success BOOLEAN DEFAULT 0,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # audit_log 表 (操作审计)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            user_id INTEGER,
            user_name TEXT,
            details TEXT,
            ip_address TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 迁移：检查并添加 notify_services 的新字段
    try:
        cursor.execute("PRAGMA table_info(notify_services)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'url' not in columns:
            cursor.execute("ALTER TABLE notify_services ADD COLUMN url TEXT")
            print("添加 notify_services.url 字段")
        if 'token' not in columns:
            cursor.execute("ALTER TABLE notify_services ADD COLUMN token TEXT")
            print("添加 notify_services.token 字段")
    except Exception as e:
        print(f"迁移 notify_services 表: {e}")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
    print("数据库迁移完成")
