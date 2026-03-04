#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试 bot_server.py 导入"""
import sys
import os

# 清除缓存
print("清除模块缓存...")
for module in list(sys.modules.keys()):
    if 'bot_server' in module:
        del sys.modules[module]

# 设置编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

try:
    print("导入 bot_server...")
    from bot_server import BotServer
    print("✅ 导入成功！")
except SyntaxError as e:
    print(f"❌ 语法错误: 行 {e.lineno}: {e.msg}")
    print(f"   内容: {e.text}")
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()
