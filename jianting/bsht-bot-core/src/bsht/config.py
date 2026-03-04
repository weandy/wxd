"""Configuration management"""
from dataclasses import dataclass
from typing import Optional


# 服务器配置
BSHT_BASE_URL = "https://rpc.benshikj.com:800"

# 音频配置
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_FRAME_SIZE = 960
DEFAULT_CHANNELS = 1

# PTT 配置
PTT_HOLD_TIMEOUT = 0.30  # 300ms 无按键 = 松开

# Jitter Buffer 配置
DEFAULT_JITTER_BUFFER_SIZE = 20  # 帧数
DEFAULT_MAX_JITTER = 30  # 最大抖动帧数

# 录音配置
RECORDING_DIR = "recordings"


@dataclass
class ServerConfig:
    """服务器配置"""
    base_url: str = BSHT_BASE_URL
    timeout: int = 30
    max_retries: int = 3


@dataclass
class AudioConfig:
    """音频配置"""
    sample_rate: int = DEFAULT_SAMPLE_RATE
    frame_size: int = DEFAULT_FRAME_SIZE
    channels: int = DEFAULT_CHANNELS
    bitrate: int = 16000  # Opus bitrate


@dataclass
class BotConfig:
    """机器人配置"""
    username: str = ""
    password: str = ""
    channel_id: int = 0
    channel_passcode: int = 0
    auto_refresh_token: bool = True


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    file: str = "bot_server.log"
    console: bool = True
