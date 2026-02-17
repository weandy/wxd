"""
音频预处理管线

对讲机通联场景优化:
- 高通滤波 (80Hz) — 滤除风噪/低频环境噪声
- 峰值归一化 — 统一音量，解决远/近距离说话音量差异大的问题

设计原则:
  录音阶段只做安全的、非破坏性的处理。
  激进降噪(RNNoise等)放在后处理阶段，避免误删关键通联内容。
"""

import numpy as np
from typing import Optional


class AudioProcessor:
    """
    对讲机音频预处理器
    
    Usage:
        processor = AudioProcessor(sample_rate=48000)
        
        # 处理单帧 PCM (20ms, 960 samples)
        processed_pcm = processor.process(raw_pcm_bytes)
        
        # 也可以单独使用某个处理步骤
        processor.enable_highpass = False  # 禁用高通滤波
    """
    
    def __init__(self, sample_rate: int = 48000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        
        # 功能开关
        self.enable_highpass = True
        self.enable_normalize = True
        
        # 高通滤波参数
        self.highpass_cutoff = 80  # Hz
        self._hp_prev_input = 0.0
        self._hp_prev_output = 0.0
        self._hp_alpha = self._calc_hp_alpha(self.highpass_cutoff)
        
        # 归一化参数
        self.target_peak_db = -3.0  # 目标峰值 dB
        self._target_amplitude = 10 ** (self.target_peak_db / 20) * 32767
        
        # AGC (自动增益控制) 平滑参数
        self._current_gain = 1.0
        self._gain_attack = 0.01   # 快速降低增益 (防削顶)
        self._gain_release = 0.001  # 缓慢提升增益 (避免噪声放大)
        self._max_gain = 10.0       # 最大增益 (防止极静音时无限放大)
        self._min_gain = 0.1        # 最小增益
    
    def _calc_hp_alpha(self, cutoff_hz: float) -> float:
        """计算一阶 RC 高通滤波系数"""
        import math
        rc = 1.0 / (2.0 * math.pi * cutoff_hz)
        dt = 1.0 / self.sample_rate
        return rc / (rc + dt)
    
    def process(self, pcm_data: bytes) -> bytes:
        """
        处理一帧 PCM 数据
        
        Args:
            pcm_data: 16-bit signed PCM bytes (little-endian)
            
        Returns:
            处理后的 PCM bytes，长度不变
        """
        if not pcm_data:
            return pcm_data
        
        samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32)
        
        # 1. 高通滤波 — 滤除低频噪声 (风噪 < 80Hz)
        if self.enable_highpass:
            samples = self._highpass_filter(samples)
        
        # 2. AGC 归一化 — 统一音量
        if self.enable_normalize:
            samples = self._agc_normalize(samples)
        
        # 裁剪到 int16 范围
        samples = np.clip(samples, -32768, 32767)
        return samples.astype(np.int16).tobytes()
    
    def _highpass_filter(self, samples: np.ndarray) -> np.ndarray:
        """
        一阶 RC 高通滤波器 (逐样本处理，保持状态)
        
        y[n] = α * (y[n-1] + x[n] - x[n-1])
        
        对讲机场景中，80Hz 以下主要是:
        - 风噪 (20-60Hz)
        - 机械振动 (30-80Hz)
        - 电源哼声 (50/60Hz)
        """
        alpha = self._hp_alpha
        output = np.empty_like(samples)
        
        prev_in = self._hp_prev_input
        prev_out = self._hp_prev_output
        
        for i in range(len(samples)):
            x = samples[i]
            prev_out = alpha * (prev_out + x - prev_in)
            prev_in = x
            output[i] = prev_out
        
        self._hp_prev_input = prev_in
        self._hp_prev_output = prev_out
        
        return output
    
    def _agc_normalize(self, samples: np.ndarray) -> np.ndarray:
        """
        自动增益控制 (AGC)
        
        比简单的峰值归一化更适合对讲机场景:
        - 快速attack: 大声信号立即降增益，防止削顶
        - 慢release: 声音变小时缓慢提升增益，避免噪声暴涨
        - 增益上限: 防止纯噪声时无限放大
        """
        peak = np.max(np.abs(samples))
        
        if peak < 1:  # 静音帧，不调整
            return samples
            
        # 计算目标增益
        desired_gain = self._target_amplitude / peak
        desired_gain = np.clip(desired_gain, self._min_gain, self._max_gain)
        
        # 平滑增益变化
        if desired_gain < self._current_gain:
            # Attack: 快速降低增益
            self._current_gain += (desired_gain - self._current_gain) * self._gain_attack * len(samples)
        else:
            # Release: 缓慢提升增益
            self._current_gain += (desired_gain - self._current_gain) * self._gain_release * len(samples)
        
        self._current_gain = np.clip(self._current_gain, self._min_gain, self._max_gain)
        
        return samples * self._current_gain
    
    def reset(self):
        """重置滤波器状态 (新通话session时调用)"""
        self._hp_prev_input = 0.0
        self._hp_prev_output = 0.0
        self._current_gain = 1.0
