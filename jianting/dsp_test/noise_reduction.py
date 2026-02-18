"""
降噪模块 (Noise Reduction)

提供多种降噪算法:
1. 谱减法 (Spectral Subtraction) - 基础，无需额外依赖
2. Wiener滤波 - 进阶
3. RNNoise - 需要安装 rnnoise库
4. DeepFilterNet - 需要安装 deepfilternet库

优先使用更强的降噪算法
"""

import numpy as np
from typing import Optional, Tuple
import sys


class TimeDomainDenoiser:
    """时域自适应降噪器
    
    基于信号能量估计的自适应滤波，更稳定可靠
    """
    
    def __init__(
        self,
        sample_rate: int = 48000,
        frame_size: int = 960,
        noise_threshold_db: float = -40.0
    ):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.noise_threshold_db = noise_threshold_db
        self.noise_threshold = 10 ** (noise_threshold_db / 20)
        
        # 噪声估计
        self.noise_floor = 0.0
        self.is_initialized = False
        self.init_frames = 0
        self.max_init_frames = 20
        
    def process(self, frame: np.ndarray) -> np.ndarray:
        """处理音频帧"""
        if len(frame) != self.frame_size:
            padded = np.zeros(self.frame_size)
            padded[:len(frame)] = frame
            frame = padded
        
        # 计算当前帧的能量
        rms = np.sqrt(np.mean(frame ** 2))
        
        # 初始化噪声估计（前20帧）
        if not self.is_initialized:
            if self.init_frames < self.max_init_frames:
                self.noise_floor = 0.9 * self.noise_floor + 0.1 * rms if self.init_frames > 0 else rms
                self.init_frames += 1
                return frame
            else:
                self.noise_floor = max(self.noise_floor, self.noise_threshold)
                self.is_initialized = True
        
        # 自适应噪声估计（非常缓慢地更新）
        if rms < self.noise_floor * 1.5:
            self.noise_floor = 0.99 * self.noise_floor + 0.01 * rms
        
        # 如果信号低于噪声阈值，静音处理
        if rms < self.noise_floor:
            return frame * 0.1
        
        # 计算信噪比
        snr = rms / (self.noise_floor + 1e-10)
        
        # 根据SNR调整增益
        if snr > 1.0:
            # 高信噪比，保持信号
            gain = 1.0
        else:
            # 低信噪比，轻微衰减
            gain = 0.5 + 0.5 * snr
        
        return frame * gain
    
    def reset(self):
        self.noise_floor = 0.0
        self.is_initialized = False
        self.init_frames = 0


class SpectralSubtraction:
    """谱减法降噪器
    
    原理: 从频谱中减去噪声谱
    优点: 轻量、实时性好
    缺点: 可能产生音乐噪声
    """
    
    def __init__(
        self,
        sample_rate: int = 48000,
        frame_size: int = 960,
        noise_frames: int = 10,
        alpha: float = 1.0,  # 进一步降低，保持自然
        beta: float = 0.5    # 大幅提高，避免失真
    ):
        """
        初始化谱减法降噪器
        
        Args:
            sample_rate: 采样率
            frame_size: 帧大小
            noise_frames: 用于估计噪声的帧数
            alpha: 过减系数 (越大降噪越强，但可能失真)
            beta: 谱 flooring系数 (防止负值)
        """
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.noise_frames = noise_frames
        self.alpha = alpha
        self.beta = beta
        
        # FFT参数 - 使用与帧大小相同的FFT
        self.nfft = frame_size
        self.window = np.hanning(frame_size)
        
        # 噪声估计
        self.noise_spectrum = None
        self.frame_count = 0
        
        # 重叠相加缓冲区
        self.input_buffer = np.zeros(frame_size)
        self.output_buffer = np.zeros(frame_size)
        
    def _frame_to_stft(self, frame: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """短时傅里叶变换"""
        # 加窗
        windowed = frame * self.window
        
        # FFT
        fft_result = np.fft.rfft(windowed, self.nfft)
        
        # 幅度和相位
        magnitude = np.abs(fft_result)
        phase = np.angle(fft_result)
        
        return magnitude, phase
    
    def _istft(self, magnitude: np.ndarray, phase: np.ndarray) -> np.ndarray:
        """逆短时傅里叶变换"""
        # 重建频谱
        spectrum = magnitude * np.exp(1j * phase)
        
        # 逆FFT
        result = np.fft.irfft(spectrum, self.nfft)
        
        # 只取frame_size部分，不加窗
        return result[:self.frame_size]
    
    def estimate_noise(self, frame: np.ndarray):
        """估计噪声频谱 (用于初始化)"""
        magnitude, _ = self._frame_to_stft(frame)
        
        if self.noise_spectrum is None:
            self.noise_spectrum = magnitude
        else:
            # 指数移动平均更新噪声谱
            self.noise_spectrum = 0.8 * self.noise_spectrum + 0.2 * magnitude
    
    def process(self, frame: np.ndarray) -> np.ndarray:
        """
        降噪处理
        
        Args:
            frame: 输入音频帧
            
        Returns:
            降噪后的音频帧
        """
        if len(frame) != self.frame_size:
            # 补零到固定长度
            padded = np.zeros(self.frame_size)
            padded[:len(frame)] = frame
            frame = padded
        
        # STFT
        magnitude, phase = self._frame_to_stft(frame)
        
        # 噪声估计 (前noise_frames帧视为噪声)
        if self.frame_count < self.noise_frames:
            self.estimate_noise(frame)
            self.frame_count += 1
            return frame
        
        # 谱减
        magnitude_cleaned = magnitude - self.alpha * self.noise_spectrum
        
        # 谱 flooring
        magnitude_cleaned = np.maximum(magnitude_cleaned, self.beta * magnitude)
        
        # 最小值限制
        magnitude_cleaned = np.maximum(magnitude_cleaned, self.beta)
        
        # ISTFT
        output = self._istft(magnitude_cleaned, phase)
        
        # 保持在原始帧长度
        return output[:len(frame)]
    
    def reset(self):
        """重置状态"""
        self.noise_spectrum = None
        self.frame_count = 0


class WienerFilter:
    """Wiener滤波降噪器
    
    比谱减法更好的主观质量，但计算稍复杂
    """
    
    def __init__(
        self,
        sample_rate: int = 48000,
        frame_size: int = 960,
        noise_frames: int = 10
    ):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.noise_frames = noise_frames
        
        self.nfft = 2048
        self.window = np.hanning(frame_size)
        
        self.noise_spectrum = None
        self.frame_count = 0
    
    def _frame_to_stft(self, frame: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        windowed = frame * self.window
        fft_result = np.fft.rfft(windowed, self.nfft)
        magnitude = np.abs(fft_result)
        phase = np.angle(fft_result)
        return magnitude, phase
    
    def _istft(self, magnitude: np.ndarray, phase: np.ndarray) -> np.ndarray:
        spectrum = magnitude * np.exp(1j * phase)
        result = np.fft.irfft(spectrum, self.nfft)
        return result[:self.frame_size] * self.window
    
    def process(self, frame: np.ndarray) -> np.ndarray:
        if len(frame) != self.frame_size:
            padded = np.zeros(self.frame_size)
            padded[:len(frame)] = frame
            frame = padded
        
        magnitude, phase = self._frame_to_stft(frame)
        
        # 噪声估计
        if self.frame_count < self.noise_frames:
            if self.noise_spectrum is None:
                self.noise_spectrum = magnitude ** 2
            else:
                self.noise_spectrum = 0.8 * self.noise_spectrum + 0.2 * (magnitude ** 2)
            self.frame_count += 1
            return frame
        
        # 计算先验信噪比 (Wiener增益)
        signal_power = magnitude ** 2
        noise_power = self.noise_spectrum
        
        # Wiener增益
        g = (signal_power - noise_power) / signal_power
        g = np.maximum(g, 0.1)  # 最小增益提高到0.1，避免过度降噪
        
        # 平滑增益 - 提高以保持更多语音细节
        g = 0.85 * g + 0.15 * 0.7
        
        # 应用增益
        magnitude_cleaned = g * magnitude
        
        # ISTFT
        output = self._istft(magnitude_cleaned, phase)
        
        # 更新噪声谱 (非常轻微)
        self.noise_spectrum = 0.99 * self.noise_spectrum + 0.01 * (magnitude ** 2)
        
        return output[:len(frame)]
    
    def reset(self):
        self.noise_spectrum = None
        self.frame_count = 0


class RNNoiseAdapter:
    """RNNoise 降噪适配器
    
    RNNoise 是一个基于RNN的降噪库，效果很好
    需要安装: pip install rnnoise
    """
    
    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self._model = None
        self._available = False
        
        try:
            import rnnoise
            self._rnnoise = rnnoise
            self._model = rnnoise.Model()
            self._available = True
            print("[降噪] 使用 RNNoise")
        except ImportError:
            print("[降噪] RNNoise 不可用，回退到谱减法")
            self._available = False
            self.fallback = SpectralSubtraction(sample_rate=sample_rate)
    
    def process(self, frame: np.ndarray) -> np.ndarray:
        if not self._available:
            return self.fallback.process(frame)
        
        # RNNoise 需要 float32, 范围 [-1, 1]
        if frame.dtype != np.float32:
            frame = frame.astype(np.float32)
        
        # 确保范围正确
        if frame.max() > 1.0 or frame.min() < -1.0:
            frame = frame / 32768.0
        
        # RNNoise 处理
        try:
            output = self._rnnoise.process_frame(frame)
            return output
        except Exception as e:
            print(f"[降噪] RNNoise 错误: {e}")
            return self.fallback.process(frame)


class NoiseReduceAdapter:
    """noisereduce 降噪适配器
    
    基于深度学习的谱门控(Spectral Gating)降噪
    需要安装: pip install noisereduce
    """
    
    def __init__(self, sample_rate: int = 48000, frame_size: int = 960):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self._available = False
        self._noisereduce = None
        
        try:
            import noisereduce
            self._noisereduce = noisereduce
            self._available = True
            print("[降噪] 使用 noisereduce (AI深度学习降噪)")
        except ImportError:
            print("[降噪] noisereduce 不可用，回退到时域降噪")
            self._available = False
            self.fallback = TimeDomainDenoiser(sample_rate, frame_size)
    
    def process(self, frame: np.ndarray) -> np.ndarray:
        if not self._available:
            return self.fallback.process(frame)
        
        # noisereduce 需要完整音频处理，不适合帧处理
        # 这里返回原始帧，在process_audio中统一处理
        return frame
    
    def process_audio(self, audio: np.ndarray) -> np.ndarray:
        """处理完整音频 - noisereduce需要一次性处理"""
        if not self._available:
            return self.fallback.process_audio(audio)
        
        try:
            # noisereduce 处理
            # stationary=True 对平稳噪声效果好
            # time_smooth_psd=0.05 平滑时间
            reduced = self._noisereduce.reduce_noise(
                y=audio,
                sr=self.sample_rate,
                stationary=True,
                n_fft=2048,
                hop_length=512,
                time_smooth_psd=0.05,
                chunk_size=8192,
                n_jobs=1
            )
            return reduced
        except Exception as e:
            print(f"[降噪] noisereduce 错误: {e}")
            return audio
    
    def reset(self):
        pass


class DeepFilterNetAdapter:
    """DeepFilterNet 降噪适配器
    
    最新的深度学习降噪算法，效果最好
    需要安装: pip install deepfilternet
    """
    
    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self._model = None
        self._available = False
        
        try:
            import deepfilter
            self._df = deepfilter
            self._model = deepfilter.DeepFilter()
            self._available = True
            print("[降噪] 使用 DeepFilterNet")
        except ImportError:
            print("[降噪] DeepFilterNet 不可用，回退到RNNoise/谱减法")
            self._available = False
            self.fallback = RNNoiseAdapter(sample_rate=sample_rate)
    
    def process(self, frame: np.ndarray) -> np.ndarray:
        if not self._available:
            return self.fallback.process(frame)
        
        try:
            return self._model.process(frame)
        except Exception as e:
            print(f"[降噪] DeepFilterNet 错误: {e}")
            return self.fallback.process(frame)


class NoiseReducer:
    """降噪处理器 (自动选择最佳算法)"""
    
    def __init__(
        self,
        sample_rate: int = 48000,
        frame_size: int = 960,
        algorithm: str = "auto"
    ):
        """
        初始化降噪器
        
        Args:
            sample_rate: 采样率
            frame_size: 帧大小
            algorithm: 算法选择 "auto", "spectral", "wiener", "rnnoise", "deepfilter"
        """
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        
        # 自动选择最佳算法
        if algorithm == "auto":
            # 优先级: noisereduce > DeepFilterNet > RNNoise > TimeDomain > Wiener > Spectral
            try:
                import noisereduce
                algorithm = "noisereduce"
            except ImportError:
                try:
                    import deepfilter
                    algorithm = "deepfilter"
                except ImportError:
                    try:
                        import rnnoise
                        algorithm = "rnnoise"
                    except ImportError:
                        algorithm = "timedomain"
        
        # 创建降噪器
        if algorithm == "noisereduce":
            self.noise_reducer = NoiseReduceAdapter(sample_rate, frame_size)
            self._use_audio_process = True  # noisereduce需要整体处理
        elif algorithm == "deepfilter":
            self.noise_reducer = DeepFilterNetAdapter(sample_rate)
            self._use_audio_process = False
        elif algorithm == "rnnoise":
            self.noise_reducer = RNNoiseAdapter(sample_rate)
            self._use_audio_process = False
        elif algorithm == "wiener":
            self.noise_reducer = WienerFilter(sample_rate, frame_size)
            self._use_audio_process = False
        elif algorithm == "spectral":
            self.noise_reducer = SpectralSubtraction(sample_rate, frame_size)
            self._use_audio_process = False
        else:  # timedomain - 最稳定可靠
            self.noise_reducer = TimeDomainDenoiser(sample_rate, frame_size)
            self._use_audio_process = False
        
        self.algorithm = algorithm
        print(f"[降噪] 初始化完成，使用算法: {algorithm}")
    
    def process(self, frame: np.ndarray) -> np.ndarray:
        """处理音频帧"""
        return self.noise_reducer.process(frame)
    
    def process_audio(self, audio: np.ndarray) -> np.ndarray:
        """处理完整音频"""
        # noisereduce需要整体处理
        if hasattr(self, '_use_audio_process') and self._use_audio_process:
            return self.noise_reducer.process_audio(audio)
        
        # 其他算法分帧处理
        frames = []
        for i in range(0, len(audio), self.frame_size):
            frame = audio[i:i + self.frame_size]
            if len(frame) < self.frame_size:
                # 补零
                padded = np.zeros(self.frame_size)
                padded[:len(frame)] = frame
                frame = padded
            processed = self.process(frame)
            frames.append(processed)
        
        # 重叠相加
        output = np.zeros(len(audio) + self.frame_size)
        weight = np.zeros(len(audio) + self.frame_size)
        
        for i, frame in enumerate(frames):
            start = i * self.frame_size
            output[start:start + self.frame_size] += frame
            weight[start:start + self.frame_size] += self.window_for_overlap_add(
                len(frame)
            )
        
        # 归一化
        weight[weight == 0] = 1
        output = output[:len(audio)] / weight[:len(audio)]
        
        return output
    
    def window_for_overlap_add(self, size: int) -> np.ndarray:
        """重叠相加窗口"""
        return np.hanning(size)
    
    def reset(self):
        """重置"""
        if hasattr(self.noise_reducer, 'reset'):
            self.noise_reducer.reset()
