"""
数据库性能分析工具
识别慢查询、缺失的索引和性能瓶颈
"""
import sqlite3
import time
from datetime import datetime
from src.database import Database

db = Database()
conn = sqlite3.connect(db.db_path)
cursor = conn.cursor()

print("="*60)
print("数据库性能分析报告")
print("="*60)
print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"数据库: {db.db_path}\n")

# 1. 检查表结构
print("1. 数据库表结构")
print("-"*60)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print(f"表数量: {len(tables)}")
for table in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
    count = cursor.fetchone()[0]
    print(f"  - {table[0]}: {count} 行")

# 2. 分析索引
print("\n2. 索引分析")
print("-"*60)
for table in tables:
    table_name = table[0]
    cursor.execute(f"PRAGMA index_list('{table_name}')")
    indexes = cursor.fetchall()
    print(f"\n{table_name} 的索引 ({len(indexes)} 个):")
    if indexes:
        for idx in indexes:
            cursor.execute(f"PRAGMA index_info('{idx[1]}')")
            info = cursor.fetchall()
            columns = [i[2] for i in info]
            print(f"  - {idx[1]}: {', '.join(columns)}")
    else:
        print("  (无索引)")

# 3. 分析查询性能
print("\n3. 常用查询性能测试")
print("-"*60)

queries = [
    ("录音列表查询", "SELECT * FROM recordings ORDER BY timestamp DESC LIMIT 20"),
    ("今日录音统计", "SELECT COUNT(*) FROM recordings WHERE DATE(timestamp) = DATE('now')"),
    ("用户录音统计", "SELECT user_id, COUNT(*) FROM recordings GROUP BY user_id LIMIT 10"),
    ("识别结果查询", "SELECT * FROM audio_records ORDER BY timestamp DESC LIMIT 10"),
    ("规则列表查询", "SELECT * FROM correction_rules ORDER BY created_at DESC LIMIT 20"),
]

slow_queries = []
for name, sql in queries:
    start = time.time()
    try:
        cursor.execute(sql)
        cursor.fetchall()
        elapsed = (time.time() - start) * 1000
        status = "[OK]" if elapsed < 100 else "[SLOW]" if elapsed < 500 else "[VERY SLOW]"
        print(f"{status} {name}: {elapsed:.2f}ms")
        if elapsed > 100:
            slow_queries.append((name, elapsed))
    except Exception as e:
        print(f"[ERROR] {name}: {e}")

# 4. 识别缺失的索引
print("\n4. 建议添加的索引")
print("-"*60)

suggested_indexes = [
    ("recordings", "idx_recordings_timestamp", "timestamp"),
    ("recordings", "idx_recordings_user_id", "user_id"),
    ("recordings", "idx_recordings_channel_id", "channel_id"),
    ("recordings", "idx_recordings_recognized", "recognized"),
    ("audio_records", "idx_audio_records_timestamp", "timestamp"),
    ("audio_records", "idx_audio_records_channel_id", "channel_id"),
    ("correction_rules", "idx_correction_rules_enabled", "is_enabled"),
]

print("\n建议为以下字段添加索引以提高查询性能:")
missing_indexes = []
for table, idx_name, column in suggested_indexes:
    # 检查索引是否已存在
    cursor.execute(f"PRAGMA index_list('{table}')")
    existing_indexes = [idx[1] for idx in cursor.fetchall()]
    if idx_name not in existing_indexes:
        print(f"  CREATE INDEX {idx_name} ON {table}({column})")
        missing_indexes.append((table, idx_name, column))
    else:
        print(f"  [OK] {idx_name} 已存在")

# 5. 性能总结
print("\n5. 性能总结")
print("-"*60)
print(f"慢查询数量: {len(slow_queries)}")
if slow_queries:
    print("慢查询列表:")
    for name, elapsed in slow_queries:
        print(f"  - {name}: {elapsed:.2f}ms")

print(f"\n缺失索引数量: {len(missing_indexes)}")
if missing_indexes:
    print("需要创建的索引:")
    for table, idx_name, column in missing_indexes:
        print(f"  - {idx_name} ON {table}({column})")

conn.close()

print("\n分析完成！")
