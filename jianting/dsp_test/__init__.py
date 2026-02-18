"""
DSP 测试模块

包含:
- vad: 语音活动检测
- noise_reduction: 降噪处理
- agc: 自动增益控制
- metrics: 量化指标计算
- dsp_chain: 处理链整合

使用:
    from dsp_test import AudioDSPChain
    
    chain = AudioDSPChain(algorithm="spectral")
    processed = chain.process_audio(audio)
"""

from .dsp_chain import AudioDSPChain, create_dsp_chain
from .vad import EnergyVAD, WebRTCVADAdapter
from .noise_reduction import NoiseReducer, SpectralSubtraction, WienerFilter
from .agc import AGCProcessor, SimpleAGC, WebRTCAGC
from .metrics import AudioMetrics

__all__ = [
    "AudioDSPChain",
    "create_dsp_chain",
    "EnergyVAD",
    "WebRTCVADAdapter",
    "NoiseReducer",
    "SpectralSubtraction",
    "WienerFilter",
    "AGCProcessor",
    "SimpleAGC",
    "WebRTCAGC",
    "AudioMetrics",
]
