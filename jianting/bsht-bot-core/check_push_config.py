"""
检查推送服务配置
"""
import sqlite3
import os
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

DB_PATH = "data/records.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("=" * 70)
print("推送服务配置检查")
print("=" * 70)

# 检查服务配置
cursor.execute("SELECT * FROM notify_services")
services = cursor.fetchall()

if services:
    columns = [desc[0] for desc in cursor.description]
    for service in services:
        service_dict = dict(zip(columns, service))
        print(f"\n服务名称: {service_dict.get('name')}")
        print(f"类型: {service_dict.get('type')}")
        print(f"URL: {service_dict.get('url')}")
        print(f"Token: {service_dict.get('token')[:20]}...  (前20字符)")
        print(f"启用: {service_dict.get('enabled')}")
else:
    print("\n❌ 未找到推送服务配置")

# 检查用户配置
cursor.execute("SELECT * FROM notify_users")
users = cursor.fetchall()

if users:
    columns = [desc[0] for desc in cursor.description]
    print(f"\n找到 {len(users)} 个推送用户:")
    for user in users:
        user_dict = dict(zip(columns, user))
        print(f"  - {user_dict.get('name')} ({user_dict.get('user_identifier')}) - 服务ID: {user_dict.get('service_id')}")
else:
    print("\n❌ 未找到推送用户配置")

# 对比 .env 配置
print("\n" + "=" * 70)
print(".env 环境变量配置")
print("=" * 70)
print(f"WXPUSH_URL: {os.getenv('WXPUSH_URL')}")
print(f"WXPUSH_TOKEN: {os.getenv('WXPUSH_TOKEN')[:20]}...  (前20字符)")
print(f"WXPUSH_TARGETS: {os.getenv('WXPUSH_TARGETS')}")

conn.close()
print("\n" + "=" * 70)
