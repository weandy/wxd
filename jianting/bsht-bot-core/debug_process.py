"""
调试工具：检查 Bot 进程检测

用于调试为什么监控 API 无法检测到 run_bot.py 进程
"""
import psutil
import sys

print("=" * 70)
print(" " * 20 + "🔍 Bot 进程检测调试")
print("=" * 70)

print(f"\nPython 版本: {sys.version}")
print(f"PSUtil 版本: {psutil.__version__}\n")

print("正在扫描所有 Python 进程...\n")

found_bots = []
all_python_procs = []

for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
    try:
        if proc.info['name'] and 'python' in proc.info['name'].lower():
            cmdline = proc.info.get('cmdline') or []
            cmdline_str = ' '.join(cmdline)

            all_python_procs.append({
                'pid': proc.info['pid'],
                'cmdline': cmdline_str
            })

            # 检查是否是 Bot 进程
            if ('run_bot' in cmdline_str or
                'bot_server' in cmdline_str or
                'multi_channel_bot' in cmdline_str):
                found_bots.append({
                    'pid': proc.info['pid'],
                    'cmdline': cmdline_str,
                    'create_time': proc.info['create_time']
                })
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
        continue

print(f"找到 {len(all_python_procs)} 个 Python 进程\n")

if all_python_procs:
    print("所有 Python 进程:")
    print("-" * 70)
    for p in all_python_procs[:10]:  # 只显示前10个
        print(f"PID {p['pid']:6d} | {p['cmdline'][:80]}")

print("\n" + "=" * 70)

if found_bots:
    print(f"\n✅ 找到 {len(found_bots)} 个 Bot 进程:")
    print("-" * 70)
    for bot in found_bots:
        print(f"PID: {bot['pid']}")
        print(f"命令: {bot['cmdline']}")
        print(f"启动时间: {bot['create_time']}")
        print()
else:
    print("\n❌ 未找到任何 Bot 进程")
    print("\n可能的原因:")
    print("1. Bot 服务未启动")
    print("2. 进程名称不匹配")
    print("3. 权限不足（尝试以管理员身份运行）")

print("=" * 70)
