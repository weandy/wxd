"""Audio related data models"""
from dataclasses import dataclass


@dataclass
class AudioFrame:
    """音频帧"""
    user_id: int = 0          # 说话者用户ID
    data: bytes = b''         # 音频数据
    timestamp: float = 0      # 时间戳
    sample_rate: int = 8000   # 采样率
    sequence: int = 0         # RTP 序列号
    end_marker: bool = False  # RTP Marker 位 (通常表示 PTT 按下)
    is_stop: bool = False     # 是否为停止包 (RX_AUDIO_STOP)
