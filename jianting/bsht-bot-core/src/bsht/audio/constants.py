"""Audio constants and configuration"""
from enum import IntEnum


# Opus 常量
OPUS_OK = 0
OPUS_APPLICATION_VOIP = 2048
OPUS_APPLICATION_AUDIO = 2049
OPUS_APPLICATION_RESTRICTED_LOWDELAY = 2051

# 音频参数
SAMPLE_RATE = 48000  # 48kHz (Fullband)
FRAME_SIZE = 960     # 20ms @ 48kHz
CHANNELS = 1         # 单声道

# PTT 配置
PTT_HOLD_TIMEOUT = 0.30  # 300ms 无按键 = 松开


class AudioDeviceState(IntEnum):
    """音频设备状态"""
    IDLE = 0
    RECORDING = 1
    PLAYING = 2
    ERROR = 3
