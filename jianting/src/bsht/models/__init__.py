# BSHT Models Package
# 数据模型层 - 高内聚、低耦合

from .user import UserProfile, TokenInfo, StatusCode
from .channel import (
    ChannelInfo, 
    UserChannel, 
    ChannelMember, 
    ChannelConnectionParams, 
    RfChannelFields
)
from .audio import AudioFrame

__all__ = [
    # User models
    'UserProfile',
    'TokenInfo', 
    'StatusCode',
    # Channel models
    'ChannelInfo',
    'UserChannel',
    'ChannelMember',
    'ChannelConnectionParams',
    'RfChannelFields',
    # Audio models
    'AudioFrame',
]
