#!/usr/bin/env python3
"""
数据库路径标准化脚本 - 将相对路径转换为绝对路径
"""
import sqlite3
import os
import sys

# Windows 控制台编码修复
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

DB_PATH = "data/records.db"


def normalize_paths():
    """标准化数据库中的所有文件路径"""
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}")
        return

    print(f"📊 正在标准化数据库路径: {DB_PATH}")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 获取所有记录
    cursor.execute("SELECT id, filepath FROM recordings")
    all_records = cursor.fetchall()

    # 找出相对路径的记录
    relative_paths = []
    for record_id, filepath in all_records:
        # 检查是否是相对路径（不包含盘符）
        if not os.path.isabs(filepath):
            relative_paths.append((record_id, filepath))

    if not relative_paths:
        print("✅ 没有发现相对路径记录")
        conn.close()
        return

    print(f"⚠️  发现 {len(relative_paths)} 条相对路径记录")
    print("=" * 60)

    # 标准化每个相对路径
    updates = 0
    duplicates = 0

    for record_id, old_path in relative_paths:
        # 转换为绝对路径
        abs_path = os.path.abspath(old_path)

        # 检查文件是否存在
        file_exists = os.path.exists(abs_path)

        # 检查是否与现有记录冲突
        cursor.execute("SELECT id FROM recordings WHERE filepath = ?", (abs_path,))
        conflicting = cursor.fetchone()

        if conflicting:
            # 有冲突，删除这条记录（保留绝对路径的）
            cursor.execute("DELETE FROM recordings WHERE id = ?", (record_id,))
            filename = os.path.basename(old_path)
            print(f"🗑️  删除重复: {filename} (相对路径)")
            duplicates += 1
        else:
            # 更新为绝对路径
            cursor.execute("UPDATE recordings SET filepath = ? WHERE id = ?", (abs_path, record_id))
            filename = os.path.basename(old_path)
            status = "✅" if file_exists else "⚠️  "
            print(f"{status} 更新: {filename} → {abs_path}")
            updates += 1

    conn.commit()

    print("\n" + "=" * 60)
    print(f"✅ 标准化完成！")
    print(f"   更新了 {updates} 条记录")
    print(f"   删除了 {duplicates} 条重复记录")

    # 显示清理后的统计
    cursor.execute("SELECT COUNT(*) FROM recordings")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM recordings WHERE recognized = 1")
    recognized = cursor.fetchone()[0]

    cursor.execute("SELECT filepath, COUNT(*) as cnt FROM recordings GROUP BY filepath HAVING cnt > 1")
    still_duplicates = cursor.fetchall()

    print(f"\n📊 数据库统计:")
    print(f"   总记录: {total}")
    print(f"   已识别: {recognized}")
    print(f"   重复记录: {len(still_duplicates)}")

    if still_duplicates:
        print(f"\n⚠️  仍有 {len(still_duplicates)} 个文件有重复记录:")
        for fp, cnt in still_duplicates:
            print(f"   {os.path.basename(fp)}: {cnt}条")

    conn.close()


if __name__ == "__main__":
    try:
        normalize_paths()
        print("\n✅ 所有操作完成！")
        print("💡 现在可以重新运行程序了")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
