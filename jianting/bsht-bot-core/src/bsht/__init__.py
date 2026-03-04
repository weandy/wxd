# BSHT Package
# 模块化重构后的代码组织

from .models import (
    StatusCode,
    UserProfile,
    TokenInfo,
    ChannelInfo,
    UserChannel,
    ChannelMember,
    RfChannelFields,
    ChannelConnectionParams,
    AudioFrame,
)

from .protocol import (
    ProtocolError,
    AudioPacketType,
    Tag,
    Heartbeat,
    RTPPacket,
    BinaryPacket,
    AX25Packet,
)

from .audio import (
    OPUS_OK,
    OPUS_APPLICATION_VOIP,
    OPUS_APPLICATION_AUDIO,
    OPUS_APPLICATION_RESTRICTED_LOWDELAY,
    SAMPLE_RATE,
    FRAME_SIZE,
    CHANNELS,
    PTT_HOLD_TIMEOUT,
    AudioDeviceState,
    AudioFormat,
    AudioDirection,
    AudioMetadata,
    AudioStats,
    audio_level_db,
)

from .config import (
    ServerConfig,
    AudioConfig,
    BotConfig,
    LoggingConfig,
    BSHT_BASE_URL,
    RECORDING_DIR,
)

from .utils import (
    setup_logger,
    get_logger,
    validate_user_id,
    validate_channel_id,
    validate_token,
    validate_nickname,
    sanitize_filename,
)

__all__ = [
    # Models
    'StatusCode',
    'UserProfile',
    'TokenInfo',
    'ChannelInfo',
    'UserChannel',
    'ChannelMember',
    'RfChannelFields',
    'ChannelConnectionParams',
    'AudioFrame',
    # Protocol
    'ProtocolError',
    'AudioPacketType',
    'Tag',
    'Heartbeat',
    'RTPPacket',
    'BinaryPacket',
    'AX25Packet',
    # Audio
    'OPUS_OK',
    'OPUS_APPLICATION_VOIP',
    'OPUS_APPLICATION_AUDIO',
    'OPUS_APPLICATION_RESTRICTED_LOWDELAY',
    'SAMPLE_RATE',
    'FRAME_SIZE',
    'CHANNELS',
    'PTT_HOLD_TIMEOUT',
    'AudioDeviceState',
    'AudioFormat',
    'AudioDirection',
    'AudioMetadata',
    'AudioStats',
    'audio_level_db',
    # Config
    'ServerConfig',
    'AudioConfig',
    'BotConfig',
    'LoggingConfig',
    'BSHT_BASE_URL',
    'RECORDING_DIR',
    # Utils
    'setup_logger',
    'get_logger',
    'validate_user_id',
    'validate_channel_id',
    'validate_token',
    'validate_nickname',
    'sanitize_filename',
]
