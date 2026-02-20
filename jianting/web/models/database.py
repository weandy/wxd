"""Web 端数据库操作封装"""

import sqlite3
import os
import bcrypt
from datetime import datetime
from typing import Optional, Dict, Any, List


def get_db_path():
    """获取数据库路径"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'data', 'records.db'
    )


def get_db(db_path=None):
    """获取数据库连接"""
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str) -> str:
    """密码哈希"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def init_default_admin(db_path=None):
    """初始化默认管理员账号（首次部署时创建）"""
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    count = cursor.fetchone()[0]

    if count == 0:
        admin_hash = hash_password('admin')
        cursor.execute("""
            INSERT INTO users (username, password_hash, role, can_listen_recordings, can_transmit, must_change_password)
            VALUES (?, ?, 'admin', 1, 1, 1)
        """, ('admin', admin_hash))
        conn.commit()
        print("[Web] 已创建默认管理员: admin / admin (首次登录需修改密码)")

    conn.close()


# ========== 用户相关 ==========

def get_user_by_username(username: str, db_path=None) -> Optional[Dict]:
    """根据用户名获取用户"""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int, db_path=None) -> Optional[Dict]:
    """根据ID获取用户"""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_login(user_id: int, db_path=None):
    """更新用户最后登录时间"""
    conn = get_db(db_path)
    conn.execute(
        "UPDATE users SET last_login = ?, last_active_at = ? WHERE id = ?",
        (datetime.now().isoformat(), datetime.now().isoformat(), user_id)
    )
    conn.commit()
    conn.close()


def get_all_users(db_path=None) -> List[Dict]:
    """获取所有用户"""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, can_listen_recordings, can_transmit, avatar, created_at, last_login, last_active_at FROM users ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ========== 登录限流 ==========

def check_login_rate_limit(ip_address: str, db_path=None) -> bool:
    """检查是否被限流（True=允许登录, False=被限制）"""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM login_attempts
        WHERE ip_address = ? AND success = 0 AND attempted_at > datetime('now', '-15 minutes')
    """, (ip_address,))
    failed = cursor.fetchone()[0]
    conn.close()
    return failed < 5


def record_login_attempt(ip_address: str, username: str, success: bool, db_path=None):
    """记录登录尝试"""
    conn = get_db(db_path)
    conn.execute(
        "INSERT INTO login_attempts (ip_address, username, success) VALUES (?, ?, ?)",
        (ip_address, username, 1 if success else 0)
    )
    conn.commit()
    conn.close()


# ========== 审计日志 ==========

def add_audit_log(action: str, user_id: int, user_name: str, details: str, ip_address: str, db_path=None):
    """添加审计日志"""
    conn = get_db(db_path)
    conn.execute("""
        INSERT INTO audit_log (action, user_id, user_name, details, ip_address)
        VALUES (?, ?, ?, ?, ?)
    """, (action, user_id, user_name, details, ip_address))
    conn.commit()
    conn.close()


# ========== Bot 状态 (IPC) ==========

def get_bot_status(db_path=None) -> Dict[str, str]:
    """获取 Bot 全部状态"""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM bot_status")
    rows = cursor.fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}


def set_bot_status(key: str, value: str, db_path=None):
    """设置 Bot 状态"""
    conn = get_db(db_path)
    conn.execute("""
        INSERT INTO bot_status (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?
    """, (key, value, datetime.now().isoformat(), value, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def send_bot_command(command: str, params: str = None, created_by: int = None, db_path=None) -> int:
    """发送 Bot 控制指令，返回指令ID"""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bot_commands (command, params, created_by)
        VALUES (?, ?, ?)
    """, (command, params, created_by))
    cmd_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return cmd_id


def poll_pending_commands(db_path=None) -> List[Dict]:
    """获取待处理指令（Bot进程轮询调用）"""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, command, params, created_by FROM bot_commands
        WHERE status = 'pending' ORDER BY created_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_command_status(cmd_id: int, status: str, result: str = None, db_path=None):
    """更新指令执行状态"""
    conn = get_db(db_path)
    conn.execute("""
        UPDATE bot_commands SET status = ?, result = ?, processed_at = ?
        WHERE id = ?
    """, (status, result, datetime.now().isoformat(), cmd_id))
    conn.commit()
    conn.close()


# ========== 录音记录 ==========

def get_recordings(page: int = 1, per_page: int = 20, channel_id: int = None,
                   user_name: str = None, keyword: str = None, db_path=None) -> Dict:
    """获取录音列表（分页+过滤）"""
    conn = get_db(db_path)
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if channel_id:
        where_clauses.append("channel_id = ?")
        params.append(channel_id)
    if user_name:
        where_clauses.append("user_name LIKE ?")
        params.append(f"%{user_name}%")
    if keyword:
        where_clauses.append("(asr_text LIKE ? OR content_normalized LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # 获取总数
    cursor.execute(f"SELECT COUNT(*) FROM recordings WHERE {where_sql}", params)
    total = cursor.fetchone()[0]

    # 获取分页数据
    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT * FROM recordings WHERE {where_sql}
        ORDER BY timestamp DESC LIMIT ? OFFSET ?
    """, params + [per_page, offset])
    rows = cursor.fetchall()
    conn.close()

    # 查询 SSRC 映射表（从 management.db）
    ssrc_mapping = _get_ssrc_mapping()

    # 处理每条记录，应用 SSRC 映射
    items = []
    for row in rows:
        item = dict(row)
        user_id = item.get('user_id', '')
        # 如果 user_id 在 SSRC 映射中存在，则替换 nickname
        if user_id and str(user_id) in ssrc_mapping:
            item['user_name'] = ssrc_mapping[str(user_id)]
        items.append(item)

    return {
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    }


def _get_ssrc_mapping() -> Dict[str, str]:
    """从 management.db 获取 SSRC 映射"""
    ssrc_mapping = {}
    try:
        # 复用 get_db_path 的计算方式，只需替换文件名
        db_dir = os.path.dirname(get_db_path())
        mdb_path = os.path.join(db_dir, 'management.db')

        if os.path.exists(mdb_path):
            conn = sqlite3.connect(mdb_path)
            cursor = conn.cursor()
            cursor.execute("SELECT ssrc, nickname FROM ssrc_mapping")
            for row in cursor.fetchall():
                ssrc_mapping[str(row[0])] = row[1]
            conn.close()
    except Exception:
        pass  # 忽略错误，返回空映射
    return ssrc_mapping


def get_recording_by_id(recording_id: int, db_path=None) -> Optional[Dict]:
    """获取单条录音"""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,))
    row = cursor.fetchone()

    if row:
        # 查询 SSRC 映射表（从 management.db）
        ssrc_mapping = _get_ssrc_mapping()

        item = dict(row)
        user_id = item.get('user_id', '')
        # 如果 user_id 在 SSRC 映射中存在，则替换 nickname
        if user_id and str(user_id) in ssrc_mapping:
            item['user_name'] = ssrc_mapping[str(user_id)]
        conn.close()
        return item

    conn.close()
    return None


def delete_recording(recording_id: int, db_path=None) -> bool:
    """删除录音"""
    conn = get_db(db_path)
    cursor = conn.cursor()
    # 获取文件路径
    cursor.execute("SELECT filepath FROM recordings WHERE id = ?", (recording_id,))
    row = cursor.fetchone()
    if row and row['filepath'] and os.path.exists(row['filepath']):
        os.remove(row['filepath'])
    cursor.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def get_today_stats(db_path=None) -> Dict:
    """获取今日统计"""
    conn = get_db(db_path)
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')

    cursor.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN recognized = 1 THEN 1 ELSE 0 END) as recognized_count
        FROM recordings WHERE timestamp LIKE ?
    """, (f"{today}%",))
    row = cursor.fetchone()
    total = row['total'] or 0
    recognized = row['recognized_count'] or 0
    rate = round(recognized / total * 100, 1) if total > 0 else 0

    conn.close()
    return {
        'total_recordings': total,
        'recognized_count': recognized,
        'recognition_rate': rate
    }
