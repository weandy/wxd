"""
Pytest conftest.py - 全局fixtures配置
"""
import pytest
import tempfile
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from web_server import app


@pytest.fixture(autouse=True)
def reset_database_singleton():
    """每个测试后重置Database单例"""
    from src import database
    original_instance = database.Database._instance
    database.Database._instance = None
    database.Database._initialized = False
    yield
    database.Database._instance = original_instance


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def test_db():
    """创建测试数据库"""
    from src.database import Database

    # 创建临时数据库文件
    fd, db_path = tempfile.mkstemp(suffix='.db', prefix='test_db_')
    os.close(fd)

    # 重置单例并创建新的数据库实例
    from src import database
    database.Database._instance = None
    database.Database._initialized = False

    db = Database(db_path=db_path)

    yield db

    # 清理
    try:
        if db:
            del db
    except:
        pass
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def test_recording_data(test_db):
    """创建测试录音数据"""
    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect(test_db.db_path)
    cursor = conn.cursor()

    # 插入测试录音数据
    now = datetime.now().isoformat()
    test_recordings = [
        (1, "recordings/test1.opus", "test1.opus", 1, "user1", "用户1", "RX", 5.2, now, 10240, 1, "测试内容1", "测试内容1", "CQ", 0.95, -20.0, 10.0),
        (2, "recordings/test2.opus", "test2.opus", 1, "user1", "用户1", "RX", 3.1, now, 6144, 1, "测试内容2", "测试内容2", "CQ", 0.88, -18.0, 12.0),
        (3, "recordings/test3.opus", "test3.opus", 1, "user2", "用户2", "RX", 8.5, now, 17408, 1, "测试内容3", "测试内容3", "QSO", 0.92, -22.0, 8.0),
    ]

    for recording in test_recordings:
        cursor.execute("""
            INSERT INTO recordings (id, filepath, filename, channel_id, user_id, user_name, recorder_type,
                                   duration, timestamp, file_size, recognized, asr_text,
                                   content_normalized, signal_type, confidence, rms_db, snr_db)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, recording)

    conn.commit()
    conn.close()

    return test_recordings


@pytest.fixture
def test_rule_data(test_db):
    """创建测试规则数据"""
    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect(test_db.db_path)
    cursor = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    test_rules = [
        (1, "测试规则1", "replace", "测试", "test", "测试替换", "general", 0, 1, 1, now, ""),
        (2, "测试规则2", "replace", "CQ", "CQ CQ", "CQ替换", "must_replace", 1, 1, 1, now, ""),
        (3, "禁用规则", "replace", "disabled", "禁用", "禁用的规则", "general", 0, 0, 1, now, ""),
    ]

    for rule in test_rules:
        cursor.execute("""
            INSERT INTO correction_rules (id, name, rule_type, pattern, replacement, description,
                                         category, priority, is_enabled, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rule)

    conn.commit()
    conn.close()

    return test_rules


@pytest.fixture
def test_push_data(test_db):
    """创建测试推送数据"""
    import sqlite3

    conn = sqlite3.connect(test_db.db_path)
    cursor = conn.cursor()

    now = "2026-03-03 12:00:00"

    # 插入测试服务
    cursor.execute("""
        INSERT INTO notify_services (id, name, type, url, token, config, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (1, "测试WxPusher", "wxpusher", "https://test.example.com/api", "test_token", "{}", 1, now, now))

    # 插入测试用户
    test_users = [
        (1, 1, "测试用户1", "UID001", "", 1, now),
        (2, 1, "测试用户2", "UID002", "keyword1,keyword2", 1, now),
        (3, 1, "禁用用户", "UID003", "", 0, now),
    ]

    for user in test_users:
        cursor.execute("""
            INSERT INTO notify_users (id, service_id, name, user_identifier, keywords, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, user)

    conn.commit()
    conn.close()

    return {"service_id": 1, "user_count": 3}
