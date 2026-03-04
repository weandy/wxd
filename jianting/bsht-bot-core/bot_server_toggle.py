"""
PTT 切换模式 - 备用方案

使用空格键切换发射状态：
- 第一次按空格：开始发射
- 第二次按空格：停止发射
- 按 Q：退出

这种方式不依赖检测"松开"事件，更可靠。
"""

def toggle_ptt_logic():
    """
    切换模式的 PTT 逻辑

    可直接替换 _start_ptt_keyboard 函数
    """
    import threading
    import time

    def keyboard_ptt_loop():
        try:
            import msvcrt

            print("🎙️ 键盘PTT已就绪 (切换模式):")
            print("  [空格]=切换发射状态")
            print("  [Q]=退出")

            is_transmitting = False

            while True:
                # 读取所有待处理的按键
                has_space = False
                has_q = False

                while msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key == b' ':
                        has_space = True
                    elif key in (b'q', b'Q'):
                        has_q = True

                # 处理退出
                if has_q:
                    print("收到退出指令")
                    if is_transmitting:
                        print("停止发射...")
                        # self.listener.stop_transmit()
                    break

                # 处理空格 - 切换状态
                if has_space:
                    is_transmitting = not is_transmitting
                    if is_transmitting:
                        print("🟢 开始发射 (再次按空格停止)")
                        # self.listener.start_transmit()
                    else:
                        print("🔴 停止发射")
                        # self.listener.stop_transmit()

                time.sleep(0.050)  # 50ms 轮询

        except ImportError:
            print("msvcrt 不可用")
        except Exception as e:
            print(f"键盘PTT异常: {e}")

    # 可以单独测试
    # keyboard_ptt_loop()


if __name__ == "__main__":
    toggle_ptt_logic()
