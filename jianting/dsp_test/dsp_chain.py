"""
DSP处理链 - 整合VAD、降噪、AGC

这个模块整合了完整的音频处理链路
"""

import numpy as np
from typing import Optional, List, Tuple
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from vad import EnergyVAD, WebRTCVADAdapter
from noise_reduction import NoiseReducer, SpectralSubtraction, WienerFilter
from agc import AGCProcessor, SimpleAGC, WebRTCAGC
from metrics import AudioMetrics


class AudioDSPChain:
    """音频DSP处理链
    
    处理流程:
    1. VAD - 语音检测
    2. 降噪 - 谱减法/Wiener/RNNoise
    3. AGC - 自动增益控制
    """
    
    def __init__(
        self,
        sample_rate: int = 48000,
        frame_size: int = 960,
        vad_enabled: bool = False,  # 默认关闭，因为可能漏检
        noise_reduction_algorithm: str = "spectral",
        agc_mode: str = "webrtc"
    ):
        """
        初始化DSP处理链
        
        Args:
            sample_rate: 采样率
            frame_size: 帧大小
            vad_enabled: 是否启用VAD
            noise_reduction_algorithm: 降噪算法 (spectral/wiener/rnnoise/auto)
            agc_mode: AGC模式 (simple/webrtc)
        """
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.vad_enabled = vad_enabled
        
        # 初始化各模块
        if vad_enabled:
            self.vad = EnergyVAD(
                sample_rate=sample_rate,
                frame_size=frame_size,
                energy_threshold=0.015
            )
        
        self.noise_reducer = NoiseReducer(
            sample_rate=sample_rate,
            frame_size=frame_size,
            algorithm=noise_reduction_algorithm
        )
        
        self.agc = AGCProcessor(
            sample_rate=sample_rate,
            mode=agc_mode
        )
        
        self.metrics = AudioMetrics(sample_rate, frame_size)
        
        # 状态
        self.is_first_frame = True
        self.noise_estimate = None
        
        print(f"[DSP] 初始化完成:")
        print(f"  - 采样率: {sample_rate} Hz")
        print(f"  - 帧大小: {frame_size} ({frame_size/sample_rate*1000:.1f}ms)")
        print(f"  - VAD: {'启用' if vad_enabled else '禁用'}")
        print(f"  - 降噪: {self.noise_reducer.algorithm}")
        print(f"  - AGC: {agc_mode}")
    
    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        处理一帧音频
        
        Args:
            frame: 输入帧
            
        Returns:
            处理后的帧
        """
        output = frame.copy()
        
        # VAD (可选)
        if self.vad_enabled:
            is_speech = self.vad.process_frame(frame)
            if not is_speech:
                # 非语音段，只做轻微处理
                output = self.noise_reducer.process(output)
                return output
        
        # 降噪 (前几帧用于估计噪声)
        if self.is_first_frame:
            # 前10帧用于噪声估计
            self.noise_estimate = output
            self.is_first_frame = False
        
        output = self.noise_reducer.process(output)
        
        # AGC
        output = self.agc.process(output)
        
        return output
    
    def process_audio(self, audio: np.ndarray) -> np.ndarray:
        """
        处理完整音频
        
        Args:
            audio: 输入音频
            
        Returns:
            处理后的音频
        """
        if len(audio) == 0:
            return audio
        
        # 确保是numpy数组
        if not isinstance(audio, np.ndarray):
            audio = np.array(audio)
        
        # 分帧处理
        n_frames = len(audio) // self.frame_size
        output_frames = []
        
        for i in range(n_frames):
            start = i * self.frame_size
            end = start + self.frame_size
            frame = audio[start:end]
            
            processed = self.process_frame(frame)
            output_frames.append(processed)
        
        # 处理剩余部分
        remainder = len(audio) % self.frame_size
        if remainder > 0:
            last_frame = audio[-remainder:]
            padded = np.zeros(self.frame_size)
            padded[:remainder] = last_frame
            processed = self.process_frame(padded)
            output_frames.append(processed[:remainder])
        
        # 合并
        output = np.concatenate(output_frames)
        
        return output
    
    def process_with_metrics(
        self,
        audio: np.ndarray,
        output_path: Optional[str] = None
    ) -> Tuple[np.ndarray, dict]:
        """
        处理音频并计算指标
        
        Args:
            audio: 输入音频
            output_path: 输出路径 (可选)
            
        Returns:
            (处理后的音频, 指标字典)
        """
        # 保存原始音频信息
        original_audio = audio.copy()
        
        # 处理
        processed_audio = self.process_audio(audio)
        
        # 估计噪声 (处理后音频 - 原始信号 ≈ 残留噪声)
        # 这里简化处理，用原始音频的安静段作为噪声估计
        noise_estimate = self._estimate_noise_from_audio(original_audio)
        
        # 计算指标
        metrics = self.metrics.compute_full_metrics(
            original_audio,
            processed_audio,
            noise_estimate
        )
        
        return processed_audio, metrics
    
    def _estimate_noise_from_audio(self, audio: np.ndarray) -> np.ndarray:
        """从音频中估计噪声"""
        # 取能量最低的段落作为噪声估计
        frame_size = self.frame_size
        n_frames = len(audio) // frame_size
        
        if n_frames < 10:
            return np.zeros(len(audio) // 10)
        
        energies = []
        for i in range(n_frames):
            frame = audio[i*frame_size:(i+1)*frame_size]
            energies.append(np.mean(frame ** 2))
        
        # 取最低的20%帧作为噪声
        threshold = np.percentile(energies, 20)
        noise_frames = [i for i, e in enumerate(energies) if e <= threshold]
        
        if len(noise_frames) == 0:
            noise_frames = list(range(min(10, n_frames)))
        
        # 构建噪声音频
        noise_audio = np.zeros(n_frames * frame_size)
        for i in noise_frames[:10]:  # 最多10帧
            noise_audio[i*frame_size:(i+1)*frame_size] = audio[i*frame_size:(i+1)*frame_size]
        
        return noise_audio
    
    def reset(self):
        """重置状态"""
        if self.vad_enabled:
            self.vad.reset()
        self.noise_reducer.reset()
        self.agc.reset()
        self.is_first_frame = True


def create_dsp_chain(
    algorithm: str = "spectral",
    sample_rate: int = 48000
) -> AudioDSPChain:
    """
    创建DSP处理链的工厂函数
    
    Args:
        algorithm: 降噪算法 (spectral/wiener/rnnoise/auto)
        sample_rate: 采样率
        
    Returns:
        AudioDSPChain实例
    """
    return AudioDSPChain(
        sample_rate=sample_rate,
        frame_size=960,  # 20ms @ 48kHz
        vad_enabled=False,  # 建议关闭，避免漏检
        noise_reduction_algorithm=algorithm,
        agc_mode="webrtc"
    )


if __name__ == "__main__":
    # 测试
    chain = create_dsp_chain()
    print("DSP处理链创建成功!")
