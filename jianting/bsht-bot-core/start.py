#!/usr/bin/env python3
"""
BSHT Bot 统一启动脚本

可以同时启动 Web 平台和 Bot 机器人，或单独启动其中一个。
实时显示所有日志输出，方便调试。

Usage:
    python start.py               # 同时启动 Web + Bot
    python start.py --web-only    # 只启动 Web
    python start.py --bot-only    # 只启动 Bot
    python start.py --status      # 查看运行状态
    python start.py --stop        # 停止所有服务
"""
import sys
import os
import time
import signal
import subprocess
import argparse
import threading
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))


class ServiceManager:
    """服务管理器"""

    def __init__(self):
        self.processes = {}
        self.root_dir = ROOT_DIR
        self.output_threads = {}
        self.running = True

    def _stream_output(self, name, proc):
        """实时输出子进程日志"""
        try:
            for line in iter(proc.stdout.readline, ''):
                if not line or not self.running:
                    break
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] [{name.upper()}] {line}", end='', flush=True)
        except Exception:
            pass

    def start_web(self):
        """启动 Web 服务"""
        if 'web' in self.processes and self.processes['web'].poll() is None:
            print("✅ Web 服务已在运行")
            return True

        print("🌐 启动 Web 服务...")
        web_cmd = [sys.executable, "web_server.py"]
        web_proc = subprocess.Popen(
            web_cmd,
            cwd=self.root_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        self.processes['web'] = web_proc

        # 启动输出线程
        output_thread = threading.Thread(
            target=self._stream_output,
            args=('web', web_proc),
            daemon=True
        )
        output_thread.start()
        self.output_threads['web'] = output_thread

        # 等待启动
        time.sleep(2)
        if web_proc.poll() is None:
            print("✅ Web 服务启动成功: http://localhost:8000\n")
            return True
        else:
            print("❌ Web 服务启动失败\n")
            return False

    def start_bot(self):
        """启动 Bot 服务"""
        if 'bot' in self.processes and self.processes['bot'].poll() is None:
            print("✅ Bot 服务已在运行")
            return True

        print("🤖 启动 Bot 服务...")
        bot_cmd = [sys.executable, "run_bot.py"]
        bot_proc = subprocess.Popen(
            bot_cmd,
            cwd=self.root_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        self.processes['bot'] = bot_proc

        # 启动输出线程
        output_thread = threading.Thread(
            target=self._stream_output,
            args=('bot', bot_proc),
            daemon=True
        )
        output_thread.start()
        self.output_threads['bot'] = output_thread

        # 等待启动
        time.sleep(3)
        if bot_proc.poll() is None:
            print("✅ Bot 服务启动成功\n")
            return True
        else:
            print("❌ Bot 服务启动失败\n")
            return False

    def stop_all(self):
        """停止所有服务"""
        self.running = False

        if not self.processes:
            print("没有运行中的服务")
            return

        print("\n🛑 停止所有服务...")

        for name, proc in self.processes.items():
            if proc.poll() is None:
                print(f"  停止 {name.upper()}...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        self.processes.clear()
        self.output_threads.clear()
        print("✅ 所有服务已停止\n")

    def get_status(self):
        """获取服务状态"""
        import psutil

        print("\n" + "=" * 60)
        print("📊 BSHT Bot 服务状态")
        print("=" * 60)

        # 检查 Web 服务
        web_running = False
        web_port = 8000
        for conn in psutil.net_connections():
            if conn.laddr.port == web_port and conn.status == 'LISTEN':
                web_running = True
                break

        print(f"\n🌐 Web 服务: {'✅ 运行中' if web_running else '❌ 未运行'}")
        if web_running:
            print(f"   访问地址: http://localhost:{web_port}")
            print(f"   登录账号: admin / admin123")

        # 检查 Bot 服务
        bot_running = False
        bot_pid = None
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info.get('cmdline') or [])
                if 'run_bot' in cmdline or 'bot_server' in cmdline or 'multi_channel_bot' in cmdline:
                    bot_running = True
                    bot_pid = proc.info['pid']
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        print(f"\n🤖 Bot 服务: {'✅ 运行中' if bot_running else '❌ 未运行'}")
        if bot_running:
            print(f"   进程 PID: {bot_pid}")

        print("\n" + "=" * 60 + "\n")

        return web_running, bot_running

    def run_interactive(self):
        """交互式运行"""
        print("\n" + "=" * 70)
        print(" " * 20 + "🚀 BSHT Bot 启动中...")
        print("=" * 70 + "\n")

        # 启动服务
        web_ok = self.start_web()
        bot_ok = self.start_bot()

        if not (web_ok and bot_ok):
            print("\n⚠️ 部分服务启动失败，按 Ctrl+C 退出...")
            time.sleep(2)
            self.stop_all()
            return 1

        print("\n" + "=" * 70)
        print(" " * 15 + "✅ 所有服务已启动成功")
        print("=" * 70)
        print("\n📋 服务信息:")
        print("   🌐 Web 平台: http://localhost:8000")
        print("   🤖 Bot 服务: 运行中")
        print("   👤 登录账号: admin / admin123")
        print("\n💡 管理命令:")
        print("   python start.py --status   查看服务状态")
        print("   python start.py --stop     停止所有服务")
        print("\n📝 日志说明:")
        print("   [WEB]  - Web 服务日志（绿色时间戳）")
        print("   [BOT]  - Bot 服务日志（绿色时间戳）")
        print("\n" + "=" * 70)
        print("按 Ctrl+C 停止所有服务\n")

        # 信号处理
        def signal_handler(sig, frame):
            print("\n\n" + "=" * 70)
            print("收到停止信号，正在关闭所有服务...")
            print("=" * 70 + "\n")
            self.stop_all()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # 持续运行，监控进程
        try:
            while self.running:
                # 检查进程状态
                for name, proc in list(self.processes.items()):
                    if proc.poll() is not None:
                        print(f"\n⚠️  [{datetime.now().strftime('%H:%M:%S')}] {name.upper()} 服务异常停止，正在重启...")
                        if name == 'web':
                            self.start_web()
                        elif name == 'bot':
                            self.start_bot()

                time.sleep(2)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_all()

        return 0


def main():
    """主入口"""
    parser = argparse.ArgumentParser(description='BSHT Bot 统一启动脚本')
    parser.add_argument('--web-only', action='store_true',
                        help='只启动 Web 服务')
    parser.add_argument('--bot-only', action='store_true',
                        help='只启动 Bot 服务')
    parser.add_argument('--status', action='store_true',
                        help='查看服务状态')
    parser.add_argument('--stop', action='store_true',
                        help='停止所有服务')

    args = parser.parse_args()

    manager = ServiceManager()

    # 查看状态
    if args.status:
        manager.get_status()
        return 0

    # 停止服务
    if args.stop:
        manager.stop_all()
        return 0

    # 单独启动 Web
    if args.web_only:
        if not manager.start_web():
            return 1
        print("\n按 Ctrl+C 停止服务...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            manager.stop_all()
        return 0

    # 单独启动 Bot
    if args.bot_only:
        if not manager.start_bot():
            return 1
        print("\n按 Ctrl+C 停止服务...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            manager.stop_all()
        return 0

    # 同时启动 Web + Bot（默认）
    return manager.run_interactive()


if __name__ == "__main__":
    sys.exit(main())
