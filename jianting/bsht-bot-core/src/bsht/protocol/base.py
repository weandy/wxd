"""Protocol related exceptions and enums"""
import enum


class ProtocolError(Exception):
    """协议错误异常"""
    pass


class AudioPacketType(enum.IntEnum):
    """音频包类型 (参考 EnumC6128n1.java)"""
    UNKNOWN = 0
    TX_AUDIO = 1        # 发射音频
    TX_AUDIO_STOP = 2   # 发射停止
    RX_AUDIO = 3        # 接收音频
    RX_AUDIO_STOP = 4   # 接收停止
    SET_SIGN_DATA = 5   # 设置签名数据


class Tag(enum.IntEnum):
    """二进制包标签"""
    UID = 2
    CHECK = 39
    CHANNEL = 8
