"""
项目自定义异常模块
定义项目专用的异常类型，便于异常处理细化
"""
from typing import Optional


class BSHTError(Exception):
    """BSHT基础异常"""
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.code = code


class TokenExpiredError(BSHTError):
    """Token过期异常"""
    def __init__(self, message: str = "Token已过期"):
        super().__init__(message, code="TOKEN_EXPIRED")


class AuthenticationError(BSHTError):
    """认证失败异常"""
    def __init__(self, message: str = "认证失败"):
        super().__init__(message, code="AUTH_FAILED")


class NetworkError(BSHTError):
    """网络请求异常"""
    def __init__(self, message: str = "网络请求失败"):
        super().__init__(message, code="NETWORK_ERROR")


class AudioProcessingError(BSHTError):
    """音频处理异常"""
    def __init__(self, message: str = "音频处理失败"):
        super().__init__(message, code="AUDIO_ERROR")


class ASRError(AudioProcessingError):
    """语音识别异常"""
    def __init__(self, message: str = "语音识别失败"):
        super().__init__(message)
        self.code = "ASR_ERROR"


class DSPError(AudioProcessingError):
    """DSP处理异常"""
    def __init__(self, message: str = "DSP处理失败"):
        super().__init__(message)
        self.code = "DSP_ERROR"


class DatabaseError(BSHTError):
    """数据库操作异常"""
    def __init__(self, message: str = "数据库操作失败"):
        super().__init__(message, code="DB_ERROR")


class ConfigurationError(BSHTError):
    """配置错误异常"""
    def __init__(self, message: str = "配置错误"):
        super().__init__(message, code="CONFIG_ERROR")


class ProtocolError(BSHTError):
    """协议解析异常"""
    def __init__(self, message: str = "协议解析错误"):
        super().__init__(message, code="PROTOCOL_ERROR")
