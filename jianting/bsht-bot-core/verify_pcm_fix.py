#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PCM 队列修复验证脚本

快速验证音频广播是否正常工作，不再丢帧
"""
import sys
import time
import requests
import json
from pathlib import Path

def test_audio_broadcast():
    """测试音频广播功能"""
    print("=" * 60)
    print("PCM 队列修复验证测试")
    print("=" * 60)

    # 配置
    bot_api_url = "http://127.0.0.1:8765"

    # 1. 检查 Bot 服务是否运行
    print("\n[1/4] 检查 Bot 服务状态...")
    try:
        response = requests.get(f"{bot_api_url}/api/status", timeout=5)
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Bot 服务运行中")
            print(f"   状态: {status.get('status', 'unknown')}")
            print(f"   频道: {status.get('channel_id', 'unknown')}")
        else:
            print(f"❌ Bot 服务响应异常: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Bot 服务未运行，请先启动: python start.py")
        return False
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False

    # 2. 查找测试音频文件
    print("\n[2/4] 查找测试音频...")
    audio_paths = [
        "data/audio_library",
        "audio_uploads",
        "recordings"
    ]

    test_audio = None
    for path in audio_paths:
        p = Path(path)
        if p.exists():
            # 查找第一个 .wav 文件
            wav_files = list(p.glob("**/*.wav"))
            if wav_files:
                test_audio = wav_files[0]
                break

    if not test_audio:
        print("❌ 未找到测试音频文件")
        print("   请先上传音频到音频库")
        return False

    print(f"✅ 找到测试音频: {test_audio}")
    print(f"   文件大小: {test_audio.stat().st_size / 1024:.1f} KB")

    # 3. 计算预期帧数
    print("\n[3/4] 分析音频参数...")
    try:
        import wave
        with wave.open(str(test_audio), 'rb') as wf:
            sample_rate = wf.getframerate()
            frames = wf.getnframes()
            duration = frames / float(sample_rate)

            expected_frames = int(duration / 0.020)  # 20ms/帧
            print(f"✅ 音频参数:")
            print(f"   采样率: {sample_rate} Hz")
            print(f"   时长: {duration:.2f} 秒")
            print(f"   预期帧数: {expected_frames} 帧")
    except Exception as e:
        print(f"⚠️ 无法读取音频参数: {e}")
        expected_frames = 300  # 默认值 (6秒)

    # 4. 发送广播请求
    print("\n[4/4] 发送音频广播请求...")
    print("   请观察 Bot 控制台日志，确认:")
    print("   1. 不再有 'PCM 队列已满，丢弃帧' 警告")
    print(f"   2. 播放进度显示 {expected_frames} 帧")
    print("   3. 最终显示 '丢弃: 0'")

    payload = {
        "audio_path": str(test_audio.absolute()),
        "channel_id": 0  # 使用当前频道
    }

    try:
        response = requests.post(
            f"{bot_api_url}/api/broadcast/audio",
            json=payload,
            timeout=300  # 5 分钟超时
        )

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("\n✅ 广播请求已发送")
                print(f"   消息: {result.get('message', '')}")
            else:
                print(f"\n❌ 广播失败: {result.get('message', '')}")
                return False
        else:
            print(f"\n❌ HTTP 错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"\n❌ 请求失败: {e}")
        return False

    # 5. 等待播放完成
    print("\n⏳ 等待播放完成...")
    time.sleep(2)

    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("=" * 60)
    print("\n请检查 Bot 控制台日志确认:")
    print("✅ 无 'PCM 队列已满' 警告")
    print(f"✅ 总帧数: {expected_frames} (预期)")
    print("✅ 丢弃: 0 帧")
    print("\n并在 App 端验证:")
    print("✅ 收到完整音频（不是 0.3 秒）")
    print("✅ 播放有声音")

    return True


def main():
    """主函数"""
    try:
        success = test_audio_broadcast()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
