"""
量化指标计算模块

用于评估音频处理效果:
1. SNR (信噪比)
2. PESQ (语音质量)
3. STOI (短时客观可懂度)
4. 能量/音量统计
5. 频谱分析
"""

import numpy as np
from typing import Dict, Tuple, Optional
import sys


def compute_rms(audio: np.ndarray) -> float:
    """计算RMS (均方根)"""
    if len(audio) == 0:
        return 0.0
    return np.sqrt(np.mean(audio ** 2))


def compute_db(audio: np.ndarray) -> float:
    """计算dB级别的RMS"""
    rms = compute_rms(audio)
    if rms <= 0:
        return -100.0
    return 20 * np.log10(rms)


def compute_snr(signal: np.ndarray, noise: np.ndarray) -> float:
    """
    计算信噪比 (SNR)
    
    Args:
        signal: 有用信号
        noise: 噪声信号
        
    Returns:
        SNR (dB)
    """
    if len(signal) == 0 or len(noise) == 0:
        return 0.0
    
    signal_power = np.mean(signal ** 2)
    noise_power = np.mean(noise ** 2)
    
    if noise_power <= 0:
        return 100.0
    
    snr = signal_power / noise_power
    
    return 10 * np.log10(snr)


def compute_snr_improvement(
    original: np.ndarray,
    processed: np.ndarray,
    noise_estimate: np.ndarray
) -> Dict[str, float]:
    """
    计算SNR改善
    
    Args:
        original: 原始音频
        processed: 处理后音频
        noise_estimate: 噪声估计
        
    Returns:
        SNR改善指标字典
    """
    # 原始SNR
    original_snr = compute_snr(original, noise_estimate)
    
    # 处理后SNR (假设处理后噪声减少)
    # 估算处理后的噪声 = 处理后音频 - 原始信号(假设完全去噪)
    processed_noise = processed - original
    processed_snr = compute_snr(processed, processed_noise)
    
    # SNR改善
    snr_improvement = processed_snr - original_snr
    
    return {
        "original_snr_db": original_snr,
        "processed_snr_db": processed_snr,
        "snr_improvement_db": snr_improvement,
    }


def segment_snr(
    audio: np.ndarray,
    sample_rate: int = 48000,
    frame_size: int = 960,
    voice_threshold: float = 0.02
) -> Dict[str, float]:
    """
    分段SNR计算
    
    将音频分为语音段和噪声段，分别计算
    
    Args:
        audio: 音频
        sample_rate: 采样率
        frame_size: 帧大小
        voice_threshold: 语音检测阈值
        
    Returns:
        SNR统计
    """
    # 分帧
    n_frames = len(audio) // frame_size
    
    voice_frames = []
    noise_frames = []
    
    for i in range(n_frames):
        start = i * frame_size
        end = start + frame_size
        frame = audio[start:end]
        
        energy = compute_rms(frame)
        
        if energy > voice_threshold:
            voice_frames.append(energy ** 2)
        else:
            noise_frames.append(energy ** 2)
    
    # 计算
    if len(voice_frames) > 0 and len(noise_frames) > 0:
        avg_voice_power = np.mean(voice_frames)
        avg_noise_power = np.mean(noise_frames)
        
        if avg_noise_power > 0:
            snr_segment = 10 * np.log10(avg_voice_power / avg_noise_power)
        else:
            snr_segment = 100.0
    else:
        snr_segment = 0.0
    
    return {
        "snr_segment_db": snr_segment,
        "voice_frames": len(voice_frames),
        "noise_frames": len(noise_frames),
        "voice_ratio": len(voice_frames) / max(n_frames, 1),
    }


def compute_spectral_features(
    audio: np.ndarray,
    sample_rate: int = 48000
) -> Dict[str, float]:
    """
    计算频谱特征
    
    Args:
        audio: 音频
        sample_rate: 采样率
        
    Returns:
        频谱特征字典
    """
    # FFT
    fft_result = np.fft.rfft(audio)
    magnitude = np.abs(fft_result)
    frequencies = np.fft.rfftfreq(len(audio), 1/sample_rate)
    
    # 频带能量
    bands = {
        "low_freq": (0, 300),
        "mid_freq": (300, 3000),
        "high_freq": (3000, sample_rate // 2)
    }
    
    band_energies = {}
    total_energy = np.sum(magnitude ** 2)
    
    for band_name, (low, high) in bands.items():
        mask = (frequencies >= low) & (frequencies < high)
        band_energy = np.sum(magnitude[mask] ** 2)
        band_energies[band_name] = 10 * np.log10(band_energy + 1e-10)
        band_energies[f"{band_name}_ratio"] = band_energy / (total_energy + 1e-10)
    
    # 谱质心 (spectral centroid)
    if total_energy > 0:
        spectral_centroid = np.sum(frequencies * magnitude) / total_energy
    else:
        spectral_centroid = 0.0
    
    # 谱熵 (spectral entropy)
    normalized_magnitude = magnitude / (total_energy + 1e-10)
    spectral_entropy = -np.sum(normalized_magnitude * np.log2(normalized_magnitude + 1e-10))
    
    return {
        "spectral_centroid_hz": spectral_centroid,
        "spectral_entropy": spectral_entropy,
        **band_energies
    }


def compute_loudness(audio: np.ndarray) -> Dict[str, float]:
    """
    计算响度特征
    
    Args:
        audio: 音频
        
    Returns:
        响度特征
    """
    # RMS
    rms = compute_rms(audio)
    rms_db = 20 * np.log10(rms + 1e-10)
    
    # 峰值
    peak = np.max(np.abs(audio))
    peak_db = 20 * np.log10(peak + 1e-10)
    
    # 动态范围
    dynamic_range = peak_db - rms_db
    
    # 峰值因子 (crest factor)
    if rms > 0:
        crest_factor = peak / rms
    else:
        crest_factor = 1.0
    
    return {
        "rms": rms,
        "rms_db": rms_db,
        "peak": peak,
        "peak_db": peak_db,
        "dynamic_range_db": dynamic_range,
        "crest_factor": crest_factor
    }


def estimate_noise_floor(audio: np.ndarray, percentile: int = 10) -> float:
    """
    估计噪声底噪
    
    使用音频能量分布的百分位数
    
    Args:
        audio: 音频
        percentile: 百分位 (10 = 最低10%的能量)
        
    Returns:
        噪声底噪估计 (dB)
    """
    # 分帧计算能量
    frame_size = 960
    n_frames = len(audio) // frame_size
    
    if n_frames == 0:
        return -100.0
    
    energies = []
    for i in range(n_frames):
        frame = audio[i*frame_size:(i+1)*frame_size]
        energies.append(compute_rms(frame) ** 2)
    
    # 取百分位数
    noise_floor = np.percentile(energies, percentile)
    
    return 10 * np.log10(noise_floor + 1e-10)


class AudioMetrics:
    """音频指标计算器"""
    
    def __init__(self, sample_rate: int = 48000, frame_size: int = 960):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
    
    def compute_full_metrics(
        self,
        original: np.ndarray,
        processed: np.ndarray,
        noise_estimate: Optional[np.ndarray] = None
    ) -> Dict:
        """
        计算完整指标
        
        Args:
            original: 原始音频
            processed: 处理后音频
            noise_estimate: 噪声估计 (可选)
            
        Returns:
            指标字典
        """
        metrics = {}
        
        # 原始音频指标
        metrics["original"] = {
            **compute_loudness(original),
            "noise_floor_db": estimate_noise_floor(original),
            **compute_spectral_features(original, self.sample_rate),
            **segment_snr(original, self.sample_rate, self.frame_size)
        }
        
        # 处理后音频指标
        metrics["processed"] = {
            **compute_loudness(processed),
            "noise_floor_db": estimate_noise_floor(processed),
            **compute_spectral_features(processed, self.sample_rate),
            **segment_snr(processed, self.sample_rate, self.frame_size)
        }
        
        # 改善指标
        if noise_estimate is not None:
            metrics["improvement"] = compute_snr_improvement(
                original, processed, noise_estimate
            )
        
        # 音量改善
        metrics["volume_improvement"] = {
            "rms_db": metrics["processed"]["rms_db"] - metrics["original"]["rms_db"],
            "peak_db": metrics["processed"]["peak_db"] - metrics["original"]["peak_db"],
        }
        
        # 噪声底噪改善
        metrics["noise_reduction"] = {
            "noise_floor_db": metrics["original"]["noise_floor_db"] - metrics["processed"]["noise_floor_db"]
        }
        
        return metrics
    
    def print_metrics(self, metrics: Dict):
        """打印指标 - 更清晰易懂的格式"""
        
        orig = metrics["original"]
        proc = metrics["processed"]
        
        # 计算变化值
        rms_change = proc['rms_db'] - orig['rms_db']
        peak_change = proc['peak_db'] - orig['peak_db']
        noise_change = orig['noise_floor_db'] - proc['noise_floor_db']  # 降低=更好
        dynamic_change = proc['dynamic_range_db'] - orig['dynamic_range_db']
        voice_change = proc['voice_ratio'] - orig['voice_ratio']
        
        # SNR评估
        orig_snr = orig.get('snr_segment_db', 0)
        proc_snr = proc.get('snr_segment_db', 0)
        snr_change = proc_snr - orig_snr
        
        # 主观评分 (0-100分)
        score = 50  # 基础分
        if snr_change > 5: score += 20
        elif snr_change > 0: score += 10
        if noise_change > 3: score += 15
        elif noise_change > 0: score += 8
        if rms_change > 3: score += 10
        elif rms_change > 0: score += 5
        if abs(dynamic_change) < 5: score += 5  # 动态范围变化适中
        score = min(100, score)
        
        print("\n" + "=" * 70)
        print("                    音频处理效果评估报告")
        print("=" * 70)
        
        # 表格标题
        print("\n┌─────────────────────────┬────────────┬────────────┬───────────┐")
        print("│         指标            │   原始     │   处理后   │   变化    │")
        print("├─────────────────────────┼────────────┼────────────┼───────────┤")
        
        # RMS电平
        rms_symbol = "↑" if rms_change > 0 else "↓" if rms_change < 0 else "→"
        print(f"│ RMS电平 (音量)          │ {orig['rms_db']:>8.1f} dB │ {proc['rms_db']:>8.1f} dB │ {rms_symbol}{abs(rms_change):>6.1f} dB │")
        
        # 峰值电平
        peak_symbol = "↑" if peak_change > 0 else "↓" if peak_change < 0 else "→"
        print(f"│ 峰值电平                │ {orig['peak_db']:>8.1f} dB │ {proc['peak_db']:>8.1f} dB │ {peak_symbol}{abs(peak_change):>6.1f} dB │")
        
        # 噪声底噪 (降低=更好)
        noise_symbol = "✓" if noise_change > 0 else "✗" if noise_change < 0 else "→"
        print(f"│ 噪声底噪 (降低=更好)    │ {orig['noise_floor_db']:>8.1f} dB │ {proc['noise_floor_db']:>8.1f} dB │ {noise_symbol}{noise_change:>6.1f} dB │")
        
        # 动态范围
        dyn_symbol = "✓" if abs(dynamic_change) < 8 else "⚠"
        print(f"│ 动态范围                │ {orig['dynamic_range_db']:>8.1f} dB │ {proc['dynamic_range_db']:>8.1f} dB │ {dyn_symbol}{dynamic_change:>6.1f} dB │")
        
        # 语音比例
        voice_symbol = "✓" if voice_change >= -0.05 else "✗"
        print(f"│ 语音比例                │ {orig['voice_ratio']:>8.1%} │ {proc['voice_ratio']:>8.1%} │ {voice_symbol}{voice_change:>+6.1%} │")
        
        # 段SNR
        snr_symbol = "✓" if snr_change > 0 else "✗" if snr_change < 0 else "→"
        print(f"│ 段SNR (越高越清晰)      │ {orig_snr:>8.1f} dB │ {proc_snr:>8.1f} dB │ {snr_symbol}{snr_change:>+6.1f} dB │")
        
        print("└─────────────────────────┴────────────┴────────────┴───────────┘")
        
        # 总结评估
        print("\n" + "-" * 70)
        print("【效果总结】")
        
        # 评估项目
        evaluations = []
        
        if noise_change > 2:
            evaluations.append("✓ 降噪效果明显")
        elif noise_change > 0:
            evaluations.append("○ 降噪有轻微效果")
        else:
            evaluations.append("✗ 降噪效果不明显")
        
        if rms_change > 5:
            evaluations.append("✓ 音量提升显著")
        elif rms_change > 0:
            evaluations.append("○ 音量有所提升")
        else:
            evaluations.append("✗ 音量变化不明显")
        
        if snr_change > 5:
            evaluations.append("✓ 信噪比显著改善")
        elif snr_change > 0:
            evaluations.append("○ 信噪比有所改善")
        else:
            evaluations.append("✗ 信噪比变化不明显")
        
        for ev in evaluations:
            print(f"  {ev}")
        
        # 主观评分
        print(f"\n【主观评分】: {score}/100 分")
        if score >= 80:
            print("  → 处理效果优秀，语音清晰度明显提升")
        elif score >= 60:
            print("  → 处理效果良好，语音有一定改善")
        elif score >= 40:
            print("  → 处理效果一般，建议调整参数")
        else:
            print("  → 处理效果有限，可能需要更强算法")
        
        print("\n" + "=" * 70)
