"""
VAD (Voice Activity Detection) 语音活动检测模块

使用能量检测 + 过零率 的轻量级VAD算法
适合在ARM边缘设备上运行
"""

import numpy as np
from typing import Optional


class EnergyVAD:
    """基于能量的语音活动检测器
    
    特点:
    - 轻量级，适合ARM设备
    - 无需模型加载
    - 可调节灵敏度
    """
    
    def __init__(
        self,
        sample_rate: int = 48000,
        frame_size: int = 960,
        energy_threshold: float = 0.02,
        min_speech_frames: int = 3,
        min_silence_frames: int = 5
    ):
        """
        初始化VAD
        
        Args:
            sample_rate: 采样率
            frame_size: 帧大小 (960 = 20ms @ 48kHz)
            energy_threshold: 能量阈值 (0-1之间)
            min_speech_frames: 最小语音帧数 (防止噪声触发)
            min_silence_frames: 最小静音帧数 (判断语音结束)
        """
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.energy_threshold = energy_threshold
        self.min_speech_frames = min_speech_frames
        self.min_silence_frames = min_silence_frames
        
        # 状态跟踪
        self.speech_frames_count = 0
        self.silence_frames_count = 0
        self.is_speaking = False
        
        # 动态阈值调整
        self.noise_floor = 0.0
        self.adaptive_threshold = True
        
    def compute_energy(self, frame: np.ndarray) -> float:
        """计算帧能量 (RMS)"""
        if len(frame) == 0:
            return 0.0
        return np.sqrt(np.mean(frame ** 2))
    
    def compute_zero_crossing_rate(self, frame: np.ndarray) -> float:
        """计算过零率"""
        if len(frame) < 2:
            return 0.0
        return np.mean(np.abs(np.diff(np.sign(frame))))
    
    def is_speech(self, frame: np.ndarray) -> bool:
        """
        检测是否为语音
        
        Args:
            frame: 音频帧 (numpy数组)
            
        Returns:
            bool: 是否包含语音
        """
        energy = self.compute_energy(frame)
        
        # 动态阈值调整 (噪声门)
        if self.adaptive_threshold:
            if energy < self.energy_threshold:
                # 认为是噪声，更新噪声基准
                self.noise_floor = 0.7 * self.noise_floor + 0.3 * energy
            else:
                # 语音期间不更新
                pass
        
        # 使用自适应阈值
        threshold = max(
            self.energy_threshold,
            self.noise_floor * 3  # 噪声基准的3倍
        )
        
        # 能量检测
        energy_detected = energy > threshold
        
        # 过零率辅助判断 (语音通常有过零率)
        zcr = self.compute_zero_crossing_rate(frame)
        zcr_detected = zcr > 0.1  # 至少10%的过零
        
        # 综合判断
        return energy_detected and zcr_detected
    
    def process_frame(self, frame: np.ndarray) -> bool:
        """
        处理一帧，返回是否是语音段
        
        Args:
            frame: 音频帧
            
        Returns:
            bool: 当前帧是否为语音
        """
        is_speech = self.is_speech(frame)
        
        if is_speech:
            self.speech_frames_count += 1
            self.silence_frames_count = 0
            
            # 连续min_speech_frames帧才是有效语音
            if self.speech_frames_count >= self.min_speech_frames:
                self.is_speaking = True
        else:
            self.silence_frames_count += 1
            self.speech_frames_count = 0
            
            # 连续min_silence_frames帧静音才结束语音
            if self.silence_frames_count >= self.min_silence_frames:
                self.is_speaking = False
        
        return self.is_speaking
    
    def reset(self):
        """重置状态"""
        self.speech_frames_count = 0
        self.silence_frames_count = 0
        self.is_speaking = False
        self.noise_floor = 0.0


class WebRTCVADAdapter:
    """WebRTC VAD 适配器 (如果安装了webrtcvad)
    
    如果不可用，回退到EnergyVAD
    """
    
    def __init__(self, sample_rate: int = 48000, mode: int = 2):
        self.sample_rate = sample_rate
        self.mode = mode  # 0-3, 3最激进
        
        try:
            import webrtcvad
            self.vad = webrtcvad.Vad(mode)
            self.vad.set_mode(mode)
            self._use_webrtc = True
            print("[VAD] 使用 WebRTC VAD")
        except ImportError:
            print("[VAD] WebRTC VAD 不可用，使用 EnergyVAD")
            self._use_webrtc = False
            self.vad = EnergyVAD(sample_rate=sample_rate)
    
    def is_speech(self, frame: np.ndarray) -> bool:
        """检测语音"""
        if self._use_webrtc:
            # WebRTC 需要特定帧长
            if len(frame) == 160:  # 10ms @ 16kHz
                return self.vad.is_speech(frame.tobytes(), self.sample_rate)
            elif len(frame) == 480:  # 30ms @ 16kHz
                return self.vad.is_speech(frame.tobytes(), self.sample_rate)
            else:
                # 转换到16kHz
                frame_16k = self._resample(frame, self.sample_rate, 16000)
                return self.vad.is_speech(frame_16k.tobytes(), 16000)
        else:
            return self.vad.is_speech(frame)
    
    def _resample(self, audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
        """重采样"""
        if orig_rate == target_rate:
            return audio
        
        # 简单重采样
        ratio = target_rate / orig_rate
        new_length = int(len(audio) * ratio)
        
        # 线性插值
        indices = np.linspace(0, len(audio) - 1, new_length)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.int16)
    
    def process_frame(self, frame: np.ndarray) -> bool:
        """处理帧"""
        if self._use_webrtc:
            return self.is_speech(frame)
        else:
            return self.vad.process_frame(frame)
    
    def reset(self):
        """重置"""
        if not self._use_webrtc:
            self.vad.reset()
