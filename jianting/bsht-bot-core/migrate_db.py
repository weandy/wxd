"""
数据库迁移脚本
创建默认管理员账户，迁移 prompts.md 到纠错规则表
"""
import sys
from pathlib import Path
import os

# Windows 控制台设置
if sys.platform == 'win32':
    os.system('chcp 65001 > nul 2>&1')

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.database import Database, User, CorrectionRule
import bcrypt


def migrate():
    """执行数据库迁移"""
    print("[INFO] 开始数据库迁移...")

    # 初始化数据库（会自动创建新表）
    db = Database()
    print("[OK] 数据库表创建完成")

    # 1. 创建默认管理员账户
    print("\n[INFO] 创建默认管理员账户...")

    # 检查是否已存在 admin 用户
    existing_admin = db.get_user_by_username("admin")
    if existing_admin:
        print("   [WARN] 管理员账户已存在，跳过创建")
    else:
        # 生成密码哈希 (admin/admin)
        password = "admin"
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        admin_user = User(
            username="admin",
            password_hash=password_hash,
            nickname="管理员",
            role="admin",
            is_active=True
        )
        user_id = db.create_user(admin_user)
        print(f"   [OK] 管理员账户创建成功 (ID: {user_id})")
        print(f"      用户名: admin")
        print(f"      密码: admin")

    # 2. 迁移 prompts.md 到纠错规则表
    print("\n[INFO] 迁移纠错规则...")

    prompts_path = project_root / "src" / "prompts.md"
    if not prompts_path.exists():
        print("   [WARN] prompts.md 文件不存在，跳过规则迁移")
    else:
        with open(prompts_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析 prompts.md
        rules = parse_prompts(content)

        # 检查是否已有规则
        existing_rules = db.get_rules()
        if existing_rules:
            print(f"   [WARN] 已存在 {len(existing_rules)} 条规则，跳过迁移")
            print("   [TIP] 如需重新迁移，请先清空 correction_rules 表")
        else:
            # 获取 admin 用户 ID
            admin = db.get_user_by_username("admin")
            if not admin:
                print("   [ERROR] 管理员账户不存在，无法创建规则")
                return

            created_count = 0
            for rule_data in rules:
                rule = CorrectionRule(
                    **rule_data,
                    created_by=admin.id
                )
                db.create_rule(rule)
                created_count += 1

            print(f"   [OK] 成功迁移 {created_count} 条纠错规则")

    print("\n[SUCCESS] 数据库迁移完成！")


def parse_prompts(content: str) -> list:
    """解析 prompts.md 文件"""
    rules = []

    lines = content.split('\n')
    current_category = None

    for line in lines:
        line = line.strip()

        # 识别分类
        if '### 必须替换' in line:
            current_category = 'must_replace'
        elif '### 保留原文' in line:
            current_category = 'preserve'
        elif line.startswith('- ') and current_category:
            # 解析规则
            rule_text = line[2:].strip()

            if ' → ' in rule_text:
                # 替换规则: 柴友 → 台友
                parts = rule_text.split(' → ')
                if len(parts) == 2:
                    rules.append({
                        'name': f"{parts[0]}→{parts[1]}",
                        'rule_type': 'replace',
                        'pattern': parts[0].strip(),
                        'replacement': parts[1].strip(),
                        'description': f"{parts[0]} 替换为 {parts[1]}",
                        'category': current_category,
                        'priority': 0,
                        'is_enabled': True
                    })

            elif '保留:' in rule_text or rule_text.endswith('保留'):
                # 保留规则
                pattern = rule_text.replace('保留:', '').replace('保留', '').strip()
                if pattern:
                    rules.append({
                        'name': f"保留: {pattern}",
                        'rule_type': 'preserve',
                        'pattern': pattern,
                        'replacement': '',
                        'description': f"保留原文: {pattern}",
                        'category': current_category,
                        'priority': 0,
                        'is_enabled': True
                    })

    return rules


if __name__ == "__main__":
    migrate()
