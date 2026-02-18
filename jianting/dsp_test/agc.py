"""
AGC (Automatic Gain Control) 自动增益控制模块

功能:
1. 归一化音量到目标水平
2. 动态压缩/扩展
3. 峰值限制 (防止削波)

参考 WebRTC AGC 的简化实现
"""

import numpy as np
from typing import Optional


class SimpleAGC:
    """简单AGC - 归一化音量
    
    将音量归一化到目标水平
    """
    
    def __init__(
        self,
        target_level: float = 0.5,
        max_gain: float = 20.0,
        min_gain: float = 0.1
    ):
        """
        初始化简单AGC
        
        Args:
            target_level: 目标音量水平 (0-1)
            max_gain: 最大增益倍数
            min_gain: 最小增益倍数
        """
        self.target_level = target_level
        self.max_gain = max_gain
        self.min_gain = min_gain
        
        self.current_gain = 1.0
    
    def compute_level(self, audio: np.ndarray) -> float:
        """计算音频电平 (RMS)"""
        if len(audio) == 0:
            return 0.0
        return np.sqrt(np.mean(audio ** 2))
    
    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        应用AGC
        
        Args:
            audio: 输入音频
            
        Returns:
            增益调整后的音频
        """
        level = self.compute_level(audio)
        
        if level > 0:
            # 计算需要的增益
            desired_gain = self.target_level / level
            
            # 限制增益范围
            desired_gain = np.clip(desired_gain, self.min_gain, self.max_gain)
            
            # 平滑增益变化
            self.current_gain = 0.3 * desired_gain + 0.7 * self.current_gain
            
            # 应用增益
            output = audio * self.current_gain
            
            # 峰值限制
            peak = np.max(np.abs(output))
            if peak > 0.95:
                output = output * 0.95 / peak
            
            return output
        else:
            return audio
    
    def reset(self):
        """重置"""
        self.current_gain = 1.0


class WebRTCAGC:
    """WebRTC AGC 简化实现
    
    特点:
    - 模拟人耳感知 (对数缩放)
    - 压缩动态范围
    - 峰值限制
    """
    
    def __init__(
        self,
        sample_rate: int = 48000,
        target_level_db: float = -6.0,  # 目标电平 (dB) - 降低以保持自然度
        max_gain_db: float = 20.0,      # 最大增益 (dB) - 降低以避免过度放大
        compression: float = 1.5         # 压缩比 - 降低以保持动态范围
    ):
        """
        初始化 WebRTC AGC
        
        Args:
            sample_rate: 采样率
            target_level_db: 目标电平 (dB)
            max_gain_db: 最大增益 (dB)
            compression: 压缩比 (1=无压缩, 2=2:1压缩)
        """
        self.sample_rate = sample_rate
        self.target_level_db = target_level_db
        self.max_gain_db = max_gain_db
        self.compression = compression
        
        # 转换目标电平到线性
        self.target_level_linear = self._db_to_linear(target_level_db)
        self.max_gain_linear = self._db_to_linear(max_gain_db)
        
        # 增益状态
        self.current_gain_linear = 1.0
        self.gain_db = 0.0
        
        # 滤波器状态 (低通)
        self.filter_state = 0.0
        self.filter_coef = 0.1
    
    def _db_to_linear(self, db: float) -> float:
        """dB转线性"""
        return 10 ** (db / 20.0)
    
    def _linear_to_db(self, linear: float) -> float:
        """线性转dB"""
        if linear <= 0:
            return -100.0
        return 20 * np.log10(linear)
    
    def _apply_hysteresis(self, target_gain_db: float) -> float:
        """应用增益滞后 (防止抖动)"""
        hysteresis = 2.0  # dB
        
        if target_gain_db > self.gain_db + hysteresis:
            # 增益上升快
            self.gain_db = self.gain_db + hysteresis * 0.5
        elif target_gain_db < self.gain_db - hysteresis:
            # 增益下降慢 (慢压缩)
            self.gain_db = self.gain_db - hysteresis * 0.2
        else:
            # 在滞后范围内，不变
            pass
        
        # 限制范围
        self.gain_db = np.clip(self.gain_db, -self.max_gain_db, self.max_gain_db)
        
        return self.gain_db
    
    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        应用AGC
        
        Args:
            audio: 输入音频
            
        Returns:
            增益调整后的音频
        """
        if len(audio) == 0:
            return audio
        
        # 计算当前电平 (RMS)
        rms = np.sqrt(np.mean(audio ** 2))
        rms_db = self._linear_to_db(rms) if rms > 0 else -100
        
        # 计算需要的增益
        target_gain_db = self.target_level_db - rms_db
        
        # 限制最大增益
        target_gain_db = np.clip(target_gain_db, -self.max_gain_db, self.max_gain_db)
        
        # 应用滞后
        gain_db = self._apply_hysteresis(target_gain_db)
        
        # 平滑增益变化
        self.gain_db = (1 - self.filter_coef) * self.gain_db + self.filter_coef * gain_db
        
        # 转换为线性增益
        gain_linear = self._db_to_linear(self.gain_db)
        
        # 应用增益
        output = audio * gain_linear
        
        # 峰值限制 (软削波)
        peak = np.max(np.abs(output))
        if peak > 0.95:
            # 软削波
            output = np.tanh(output / peak) * 0.95
        
        return output
    
    def reset(self):
        """重置"""
        self.current_gain_linear = 1.0
        self.gain_db = 0.0
        self.filter_state = 0.0


class Limiter:
    """峰值限制器
    
    防止音频削波
    """
    
    def __init__(self, threshold: float = 0.9, attack: float = 0.001):
        """
        初始化限制器
        
        Args:
            threshold: 阈值 (0-1)
            attack: 启动时间 (秒)
        """
        self.threshold = threshold
        self.attack = attack
        
        self.envelope = 0.0
        self.release = 0.05  # 释放时间
    
    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        限制峰值
        
        Args:
            audio: 输入音频
            
        Returns:
            限制后的音频
        """
        output = np.zeros_like(audio)
        
        for i in range(len(audio)):
            # 获取当前峰值
            sample = abs(audio[i])
            
            # 峰值包络
            if sample > self.envelope:
                # 启动
                self.envelope = sample
            else:
                # 释放
                self.envelope = self.envelope * (1 - self.release)
            
            # 应用限制
            if self.envelope > self.threshold:
                gain = self.threshold / self.envelope
                output[i] = audio[i] * gain
            else:
                output[i] = audio[i]
        
        return output
    
    def reset(self):
        """重置"""
        self.envelope = 0.0


class NoiseGate:
    """噪声门 - 静音安静段落
    
    对讲机场景特别有用:
    - 检测静音段(只有噪声) → 降低增益
    - 检测语音段 → 正常增益
    """
    
    def __init__(
        self,
        sample_rate: int = 48000,
        frame_size: int = 960,
        threshold_db: float = -40.0,  # 阈值(dB)，低于此值认为是静音
        attack_time: float = 0.01,   # 启动时间(秒)
        release_time: float = 0.1    # 释放时间(秒)
    ):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.threshold_linear = 10 ** (threshold_db / 20.0)
        
        # 转换时间常数
        self.attack_coef = np.exp(-1.0 / (attack_time * sample_rate / frame_size))
        self.release_coef = np.exp(-1.0 / (release_time * sample_rate / frame_size))
        
        # 增益状态
        self.gate_gain = 1.0
        self.is_open = False
    
    def process(self, audio: np.ndarray) -> np.ndarray:
        """应用噪声门"""
        # 计算当前帧RMS
        rms = np.sqrt(np.mean(audio ** 2) + 1e-10)
        
        # 判断是否超过阈值
        target_gain = 1.0 if rms > self.threshold_linear else 0.0
        
        # 平滑过渡
        if target_gain > self.gate_gain:
            # 打开噪声门 - 快速
            self.gate_gain = self.attack_coef * self.gate_gain + (1 - self.attack_coef) * target_gain
        else:
            # 关闭噪声门 - 慢速
            self.gate_gain = self.release_coef * self.gate_gain + (1 - self.release_coef) * target_gain
        
        return audio * self.gate_gain
    
    def reset(self):
        self.gate_gain = 1.0


class EnhancedWebRTCAGC:
    """增强版 WebRTC AGC
    
    优化特性:
    - 多段动态压缩
    - 集成噪声门
    - 更平滑的增益变化
    - 人声优先模式
    """
    
    def __init__(
        self,
        sample_rate: int = 48000,
        target_level_db: float = -10.0,  # 更保守的目标电平
        max_gain_db: float = 20.0,        # 降低最大增益
        compression: float = 1.5,          # 压缩比
        noise_gate_threshold_db: float = -50.0  # 噪声门阈值（更保守）
    ):
        self.sample_rate = sample_rate
        self.target_level_db = target_level_db
        self.max_gain_db = max_gain_db
        self.compression = compression
        
        # 噪声门
        self.noise_gate = NoiseGate(
            sample_rate=sample_rate,
            threshold_db=noise_gate_threshold_db
        )
        
        # 转换
        self.target_level_linear = 10 ** (target_level_db / 20.0)
        self.max_gain_linear = 10 ** (max_gain_db / 20.0)
        
        # 增益状态
        self.gain_db = 0.0
        
        # 滤波器
        self.filter_coef = 0.15  # 稍微提高响应速度
    
    def _compute_level_db(self, audio: np.ndarray) -> float:
        """计算电平(dB)"""
        rms = np.sqrt(np.mean(audio ** 2) + 1e-10)
        return 20 * np.log10(rms + 1e-10)
    
    def process(self, audio: np.ndarray) -> np.ndarray:
        """应用增强AGC"""
        # 1. 先通过噪声门
        audio = self.noise_gate.process(audio)
        
        # 2. 计算当前电平
        current_db = self._compute_level_db(audio)
        
        # 3. 计算需要的增益 (考虑压缩)
        if current_db < self.target_level_db:
            # 低于目标电平 - 放大
            gain_db = (self.target_level_db - current_db) / self.compression
        else:
            # 高于目标电平 - 压缩
            gain_db = (self.target_level_db - current_db)
        
        # 限制增益范围
        gain_db = np.clip(gain_db, -self.max_gain_db, self.max_gain_db)
        
        # 4. 平滑增益变化
        self.gain_db = (1 - self.filter_coef) * self.gain_db + self.filter_coef * gain_db
        
        # 5. 应用增益
        gain_linear = 10 ** (self.gain_db / 20.0)
        output = audio * gain_linear
        
        # 6. 软削波
        peak = np.max(np.abs(output))
        if peak > 0.9:
            output = np.tanh(output / peak) * 0.9
        
        return output
    
    def reset(self):
        self.gain_db = 0.0
        self.noise_gate.reset()


class AGCProcessor:
    """AGC处理器 (整合多种功能)"""
    
    def __init__(
        self,
        sample_rate: int = 48000,
        mode: str = "webrtc"
    ):
        """
        初始化AGC处理器
        
        Args:
            sample_rate: 采样率
            mode: 模式 "simple", "webrtc" 或 "enhanced"
        """
        self.sample_rate = sample_rate
        
        if mode == "simple":
            self.agc = SimpleAGC()
        elif mode == "enhanced":
            self.agc = EnhancedWebRTCAGC(sample_rate)
        else:
            self.agc = WebRTCAGC(sample_rate)
        
        self.limiter = Limiter(threshold=0.95)
    
    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        应用AGC
        
        Args:
            audio: 输入音频
            
        Returns:
            处理后的音频
        """
        # AGC
        output = self.agc.process(audio)
        
        # 峰值限制
        output = self.limiter.process(output)
        
        return output
    
    def reset(self):
        """重置"""
        self.agc.reset()
        self.limiter.reset()
