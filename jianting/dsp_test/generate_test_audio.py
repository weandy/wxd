"""
生成测试音频

用于测试DSP处理效果
"""

import numpy as np
import wave
import os


def generate_noisy_speech(
    output_path: str = "inputs/test_noisy.wav",
    duration: float = 5.0,
    sample_rate: int = 48000,
    speech_db: float = -15.0,
    noise_db: float = -30.0
):
    """生成带噪声的语音测试音频"""
    print(f"生成测试音频: {output_path}")
    print(f"  时长: {duration}秒")
    print(f"  语音电平: {speech_db}dB")
    print(f"  噪声电平: {noise_db}dB")
    
    n_samples = int(duration * sample_rate)
    t = np.linspace(0, duration, n_samples)
    
    # 生成语音信号
    speech = np.zeros(n_samples)
    f0 = 150
    for harmonic in range(1, 6):
        speech += np.sin(2 * np.pi * f0 * harmonic * t) / harmonic
    
    # 添加辅音模拟
    consonants = np.random.randn(n_samples) * 0.1
    b = np.array([0.05, 0.1, 0.15, 0.1, 0.05])
    for i in range(len(consonants) - len(b) + 1):
        consonants[i] = np.sum(consonants[i:i+len(b)] * b)
    speech += consonants * 0.3
    
    # 包络
    envelope = np.ones(n_samples)
    speech_segments = [
        (0.0, 0.5, 0.0),
        (0.5, 1.5, 1.0),
        (1.5, 2.0, 0.0),
        (2.0, 3.0, 1.0),
        (3.0, 3.5, 0.0),
        (3.5, 4.5, 1.0),
        (4.5, 5.0, 0.0),
    ]
    for start, end, level in speech_segments:
        start_idx = int(start * sample_rate)
        end_idx = int(end * sample_rate)
        envelope[start_idx:end_idx] = level
    speech = speech * envelope
    
    # 归一化
    speech_rms = np.sqrt(np.mean(speech ** 2))
    speech_db_linear = 10 ** (speech_db / 20)
    speech = speech * (speech_db_linear / (speech_rms + 1e-10))
    
    # 生成噪声
    pink_noise = np.zeros(n_samples)
    b = [0.1, 0.15, 0.2, 0.15, 0.1]
    white = np.random.randn(n_samples)
    for i in range(len(white) - len(b) + 1):
        pink_noise[i] = np.sum(white[i:i+len(b)] * b)
    white_noise = np.random.randn(n_samples) * 0.3
    noise = pink_noise + white_noise
    
    # 归一化噪声
    noise_rms = np.sqrt(np.mean(noise ** 2))
    noise_db_linear = 10 ** (noise_db / 20)
    noise = noise * (noise_db_linear / (noise_rms + 1e-10))
    
    # 混合
    audio = speech + noise
    audio = np.clip(audio, -0.95, 0.95)
    
    # 保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    audio_int16 = (audio * 32767).astype(np.int16)
    
    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    
    print(f"  已保存: {output_path}")
    
    speech_power = np.mean(speech ** 2)
    noise_power = np.mean(noise ** 2)
    snr = 10 * np.log10(speech_power / (noise_power + 1e-10))
    print(f"  实际SNR: {snr:.1f} dB")
    
    return audio, noise


def generate_high_noise_speech(
    output_path: str = "inputs/test_extreme_noise.wav",
    snr_db: float = -5.0
):
    """生成极端噪声条件下的语音"""
    print(f"生成极端噪声测试音频: {output_path}")
    print(f"  目标SNR: {snr_db}dB")
    
    duration = 5.0
    sample_rate = 48000
    t = np.linspace(0, duration, int(duration * sample_rate))
    
    # 语音
    speech = np.sin(2 * np.pi * 150 * t)
    for h in [2, 3, 4, 5]:
        speech += np.sin(2 * np.pi * 150 * h * t) / h
    
    # 包络
    envelope = np.zeros_like(speech)
    speech_periods = [(0.5, 1.5), (2.0, 3.0), (3.5, 4.5)]
    for start, end in speech_periods:
        start_idx = int(start * sample_rate)
        end_idx = int(end * sample_rate)
        envelope[start_idx:end_idx] = 1.0
    speech = speech * envelope
    speech = speech / (np.max(np.abs(speech)) + 1e-10) * 0.5
    
    # 噪声
    noise = np.random.randn(len(speech)) * 0.5
    speech_power = np.mean(speech ** 2)
    target_noise_power = speech_power / (10 ** (snr_db / 10))
    noise = noise * np.sqrt(target_noise_power / (np.mean(noise ** 2) + 1e-10))
    
    # 混合
    audio = speech + noise
    audio = np.clip(audio, -0.95, 0.95)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    audio_int16 = (audio * 32767).astype(np.int16)
    
    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    
    actual_snr = 10 * np.log10(np.mean(speech ** 2) / (np.mean(noise ** 2) + 1e-10))
    print(f"  实际SNR: {actual_snr:.1f} dB")
    print(f"  已保存: {output_path}")
    
    return audio, noise


if __name__ == "__main__":
    os.makedirs("inputs", exist_ok=True)
    
    print("\n生成测试文件...")
    generate_noisy_speech("inputs/test_noisy.wav")
    generate_noisy_speech(
        "inputs/test_heavy_noise.wav",
        duration=5.0,
        speech_db=-15.0,
        noise_db=-18.0
    )
    generate_high_noise_speech("inputs/test_extreme_noise.wav", snr_db=-5.0)
    
    print("\n测试文件生成完成!")
    print("运行: python test_dsp.py inputs/test_noisy.wav")