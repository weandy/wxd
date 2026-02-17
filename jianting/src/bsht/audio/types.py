"""Audio frame types and processing utilities"""
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class AudioFormat(IntEnum):
    """音频格式"""
    PCM = 1
    OPUS = 2
    G711 = 3


class AudioDirection(IntEnum):
    """音频方向"""
    TX = 1  # 发射 (上传)
    RX = 2  # 接收 (下载)


@dataclass
class AudioMetadata:
    """音频元数据"""
    format: AudioFormat = AudioFormat.OPUS
    sample_rate: int = 48000
    channels: int = 1
    bitrate: int = 16000
    direction: AudioDirection = AudioDirection.TX


@dataclass  
class AudioStats:
    """音频统计信息"""
    frames_encoded: int = 0
    frames_decoded: int = 0
    bytes_encoded: int = 0
    bytes_decoded: int = 0
    errors: int = 0
    
    def reset(self):
        """重置统计"""
        self.frames_encoded = 0
        self.frames_decoded = 0
        self.bytes_encoded = 0
        self.bytes_decoded = 0
        self.errors = 0


def audio_level_db(data: bytes, sample_rate: int = 48000) -> float:
    """计算音频电平 (dB)"""
    import math
    import struct
    
    if len(data) < 2:
        return -100.0
    
    # 假设 16-bit PCM
    try:
        samples = struct.unpack(f'{len(data)//2}h', data)
        rms = math.sqrt(sum(s*s for s in samples) / len(samples))
        if rms > 0:
            return 20 * math.log10(rms / 32768.0)
        return -100.0
    except:
        return -100.0
