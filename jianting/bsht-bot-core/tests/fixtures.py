# 测试数据生成工具
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import wave
import tempfile


def create_test_audio(
    filepath: str = None,
    frequency: float = 1000,
    duration: float = 1.0,
    sample_rate: int = 48000,
    volume: float = 0.5,
    add_noise: float = 0.0
) -> str:
    """
    创建测试音频文件

    Args:
        filepath: 文件路径 (如果为 None，创建临时文件)
        frequency: 正弦波频率 (Hz)
        duration: 时长 (秒)
        sample_rate: 采样率
        volume: 音量 (0.0-1.0)
        add_noise: 噪声强度 (0.0-1.0)

    Returns:
        文件路径
    """
    if filepath is None:
        f = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        filepath = f.name
        f.close()

    # 生成正弦波
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = np.sin(2 * np.pi * frequency * t) * volume

    # 添加噪声
    if add_noise > 0:
        noise = np.random.randn(len(audio)) * add_noise * 0.1
        audio = audio + noise

    # 转换为 int16
    audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

    # 写入 WAV
    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())

    return filepath


def create_silent_audio(
    filepath: str = None,
    duration: float = 1.0,
    sample_rate: int = 48000
) -> str:
    """创建静音音频文件"""
    if filepath is None:
        f = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        filepath = f.name
        f.close()

    samples = int(sample_rate * duration)
    audio_int16 = np.zeros(samples, dtype=np.int16)

    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())

    return filepath


def create_noisy_audio(
    filepath: str = None,
    duration: float = 1.0,
    sample_rate: int = 48000,
    snr_db: float = 10
) -> str:
    """创建带噪声的音频文件 (用于测试降噪)"""
    if filepath is None:
        f = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        filepath = f.name
        f.close()

    t = np.linspace(0, duration, int(sample_rate * duration))

    # 信号 (语音模拟 - 多个频率)
    signal = (
        np.sin(2 * np.pi * 300 * t) * 0.3 +
        np.sin(2 * np.pi * 500 * t) * 0.2 +
        np.sin(2 * np.pi * 800 * t) * 0.1
    )

    # 噪声
    noise = np.random.randn(len(signal)) * 0.1

    # 按 SNR 混合
    signal_power = np.mean(signal ** 2)
    noise_power = np.mean(noise ** 2)
    target_noise_power = signal_power / (10 ** (snr_db / 10))
    noise = noise * np.sqrt(target_noise_power / noise_power)

    audio = signal + noise
    audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())

    return filepath


if __name__ == "__main__":
    # 测试生成
    import tempfile

    # 测试音频
    wav1 = create_test_audio(frequency=1000, duration=1.0)
    print(f"创建测试音频: {wav1}")

    # 静音音频
    wav2 = create_silent_audio(duration=0.5)
    print(f"创建静音音频: {wav2}")

    # 带噪声音频
    wav3 = create_noisy_audio(duration=1.0, snr_db=10)
    print(f"创建噪声音频: {wav3}")

    # 清理
    for f in [wav1, wav2, wav3]:
        if os.path.exists(f):
            os.unlink(f)
            print(f"已删除: {f}")
