"""Channel related data models"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ChannelInfo:
    """频道信息"""
    channel_id: int = 0
    name: str = ""
    has_passcode: bool = False
    user_count: int = 0


@dataclass
class UserChannel:
    """用户加入的频道"""
    own_user_id: int = 0
    channel_id: int = 0
    name: str = ""
    is_banned: bool = False
    is_admin: bool = False
    call_priority: int = 0
    rf_config: dict = field(default_factory=dict)


@dataclass
class ChannelMember:
    """频道成员"""
    user_id: int = 0
    is_banned: bool = False
    is_admin: bool = False
    call_priority: int = 0


@dataclass
class RfChannelFields:
    """无线电频道配置"""
    tx_freq: int = 0      # 发射频率
    rx_freq: int = 0      # 接收频率
    tx_sub_audio: int = 0 # 发送亚音
    rx_sub_audio: int = 0 # 接收亚音
    bandwidth: int = 0    # 带宽


@dataclass
class ChannelConnectionParams:
    """频道语音连接参数"""
    ip: str = ""              # 语音服务器 IP
    port: int = 0             # 语音服务器端口
    bit_rates: int = 0        # 语音比特率
    is_banned: bool = False   # 是否被禁言
    is_admin: bool = False    # 是否是管理员
    call_priority: int = 0    # 通话优先级
    rf_config: dict = field(default_factory=dict)  # 无线电配置
