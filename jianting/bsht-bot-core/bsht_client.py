import struct
import msgpack
import json
import time
import threading
import logging
import queue
import numpy as np
from typing import Optional, Tuple, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import IntEnum
from abc import ABC, abstractmethod
from ht_protocol import HTPacket, BinaryPacket, AX25Packet, Tag, ProtocolError, Heartbeat, RTPPacket

# 初始化日志
# 使用项目统一日志
try:
    from src.logging_setup import get_logger
    logger = get_logger("BSHTClient", "main")
except ImportError:
    logger = logging.getLogger("BSHTClient")
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(logging.INFO)

try:
    import httpx
except ImportError:
    print("请先安装 httpx: pip install httpx")
    exit(1)


# 优先从 models 包导入数据模型
try:
    from bsht_client.models import (
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
except ImportError:
    # 兼容：models 包不存在时使用内联定义
    from dataclasses import dataclass, field
    from enum import IntEnum

    class StatusCode(IntEnum):
        OK = 0
        ERR_NAME_OR_PASSWORD = 1
        ERR_USER_HAVE_NO_PASSWORD = 2
        ERR_NOT_LOGIN = 3
        ERR_UNCONFIRMED = 4

    @dataclass
    class UserProfile:
        user_id: int = 0
        username: str = ""
        nickname: str = ""
        email: str = ""
        photo: bytes = b''
        update_at: int = 0

    @dataclass
    class TokenInfo:
        access_token: str = ""
        access_token_expires: int = 0
        refresh_token: str = ""
        refresh_token_expires: int = 0

    @dataclass
    class ChannelInfo:
        channel_id: int = 0
        name: str = ""
        has_passcode: bool = False
        user_count: int = 0

    @dataclass
    class UserChannel:
        own_user_id: int = 0
        channel_id: int = 0
        name: str = ""
        is_banned: bool = False
        is_admin: bool = False
        call_priority: int = 0
        rf_config: dict = field(default_factory=dict)

    @dataclass
    class ChannelMember:
        user_id: int = 0
        is_banned: bool = False
        is_admin: bool = False
        call_priority: int = 0

    @dataclass
    class RfChannelFields:
        tx_freq: int = 0
        rx_freq: int = 0
        tx_sub_audio: int = 0
        rx_sub_audio: int = 0
        bandwidth: int = 0

    @dataclass
    class ChannelConnectionParams:
        ip: str = ""
        port: int = 0
        bit_rates: int = 0
        is_banned: bool = False
        is_admin: bool = False
        call_priority: int = 0
        rf_config: dict = field(default_factory=dict)

    @dataclass
    class AudioFrame:
        user_id: int = 0
        data: bytes = b''
        timestamp: float = 0
        sample_rate: int = 8000
        sequence: int = 0
        end_marker: bool = False
        is_stop: bool = False


# Protobuf 编解码器

class ProtobufCodec:
    """Protobuf 编解码器"""
    
    @staticmethod
    def encode_varint(value: int) -> bytes:
        """编码 varint"""
        result = []
        while value > 127:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value)
        return bytes(result)
    
    @staticmethod
    def decode_varint(data: bytes, pos: int) -> Tuple[int, int]:
        """解码 varint，返回 (值, 新位置)"""
        result = 0
        shift = 0
        while pos < len(data):
            byte = data[pos]
            result |= (byte & 0x7F) << shift
            pos += 1
            if not (byte & 0x80):
                break
            shift += 7
        return result, pos
    
    @classmethod
    def encode_string(cls, field_num: int, value: str) -> bytes:
        """编码 string 字段"""
        data = value.encode('utf-8')
        tag = (field_num << 3) | 2
        return bytes([tag]) + cls.encode_varint(len(data)) + data
    
    @classmethod
    def encode_bytes(cls, field_num: int, value: bytes) -> bytes:
        """编码 bytes 字段"""
        tag = (field_num << 3) | 2
        return bytes([tag]) + cls.encode_varint(len(value)) + value
    
    @classmethod
    def encode_int32(cls, field_num: int, value: int) -> bytes:
        """编码 int32 字段"""
        if value == 0:
            return b''
        tag = (field_num << 3) | 0
        return bytes([tag]) + cls.encode_varint(value)
    
    @classmethod
    def encode_uint64(cls, field_num: int, value: int) -> bytes:
        """编码 uint64 字段"""
        if value == 0:
            return b''
        tag = (field_num << 3) | 0
        return bytes([tag]) + cls.encode_varint(value)
    
    @classmethod
    def encode_bool(cls, field_num: int, value: bool) -> bytes:
        """编码 bool 字段"""
        if not value:
            return b''
        tag = (field_num << 3) | 0
        return bytes([tag, 1])
    
    @classmethod
    def encode_message(cls, field_num: int, message: bytes) -> bytes:
        """编码嵌套消息字段"""
        tag = (field_num << 3) | 2
        return bytes([tag]) + cls.encode_varint(len(message)) + message
    
    @classmethod
    def decode_message(cls, data: bytes) -> Dict[int, Any]:
        """解码 Protobuf 消息为字典"""
        result = {}
        pos = 0
        while pos < len(data):
            if pos >= len(data):
                break
            tag = data[pos]
            field_num = tag >> 3
            wire_type = tag & 0x07
            pos += 1
            
            if wire_type == 0:  # varint
                value, pos = cls.decode_varint(data, pos)
                # repeated varint: 收集到列表
                if field_num in result:
                    if not isinstance(result[field_num], list):
                        result[field_num] = [result[field_num]]
                    result[field_num].append(value)
                else:
                    result[field_num] = value
            elif wire_type == 2:  # length-delimited
                length, pos = cls.decode_varint(data, pos)
                value = data[pos:pos + length]
                pos += length
                # 尝试解码为字符串
                try:
                    decoded_str = value.decode('utf-8')
                    if all(c.isprintable() or c in '\n\r\t' for c in decoded_str):
                        value = decoded_str
                except (UnicodeDecodeError, AttributeError):
                    # 解码失败，保留原始字节
                    pass
                # repeated 字段: 收集到列表
                if field_num in result:
                    if not isinstance(result[field_num], list):
                        result[field_num] = [result[field_num]]
                    result[field_num].append(value)
                else:
                    result[field_num] = value
            elif wire_type == 5:  # 32-bit fixed
                value = struct.unpack('<I', data[pos:pos+4])[0]
                pos += 4
                if field_num in result:
                    if not isinstance(result[field_num], list):
                        result[field_num] = [result[field_num]]
                    result[field_num].append(value)
                else:
                    result[field_num] = value
            else:
                break
        
        return result


# ==================== gRPC 客户端 ====================

class GrpcClient:
    """gRPC 底层客户端"""
    
    BASE_URL = "https://rpc.benshikj.com:800"
    CONTENT_TYPE = "application/grpc"
    
    def __init__(self, timeout: float = 30.0):
        self._client = httpx.Client(http2=True, verify=False, timeout=timeout)
    
    def _build_frame(self, message: bytes, compressed: bool = False) -> bytes:
        """构建 gRPC 数据帧"""
        compressed_flag = 1 if compressed else 0
        length = struct.pack('>I', len(message))
        return bytes([compressed_flag]) + length + message
    
    def _parse_response(self, data: bytes) -> Tuple[bytes, dict]:
        """解析 gRPC 响应"""
        if len(data) < 5:
            return b'', {}
        
        length = struct.unpack('>I', data[1:5])[0]
        message = data[5:5 + length]
        
        remaining = data[5 + length:]
        trailers = {}
        if remaining:
            try:
                trailer_text = remaining.decode('utf-8')
                for line in trailer_text.strip().split('\r\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        trailers[key.strip()] = value.strip()
            except (UnicodeDecodeError, AttributeError) as e:
                # 忽略 trailer 解析错误
                pass
        
        return message, trailers
    
    def request(self, service: str, method: str, 
                body: bytes, 
                access_token: Optional[str] = None) -> Tuple[bytes, dict]:
        """发送 gRPC 请求"""
        url = f"{self.BASE_URL}/{service}/{method}"
        
        headers = {
            "user-agent": "grpc-java-okhttp/1.77.0",
            "content-type": self.CONTENT_TYPE,
            "te": "trailers",
            "grpc-accept-encoding": "gzip",
            "hl": "zh-CN",
            "user_agent": "com.benshikj.ht/2.9.2.1",
        }
        
        if access_token:
            headers["access_token"] = access_token
        
        grpc_body = self._build_frame(body)
        response = self._client.post(url, content=grpc_body, headers=headers)
        
        # gRPC trailers 可能在 HTTP headers 或响应体末尾
        grpc_status = response.headers.get('grpc-status')
        grpc_message = response.headers.get('grpc-message', '')
        
        # 解析响应消息体
        message, trailers = self._parse_response(response.content)
        
        # 如果 headers 中没有 trailers，尝试从响应体解析
        if grpc_status is None:
            if trailers:
                grpc_status = trailers.get('grpc-status', '0')
                grpc_message = trailers.get('grpc-message', '')
            else:
                # HTTP 200 + 无明确错误 = 成功
                # (空的 gRPC 响应表示成功，如 JoinChannel, QuitChannel 等)
                if response.status_code == 200:
                    grpc_status = '0'
                    grpc_message = ''
                else:
                    grpc_status = '-1'
                    grpc_message = f'HTTP {response.status_code}'
        
        return message, {
            'grpc-status': grpc_status,
            'grpc-message': grpc_message
        }
    
    def close(self):
        """关闭客户端"""
        self._client.close()


# ==================== Token 管理器 ====================

class TokenManager:
    """Token 自动刷新管理器"""
    
    # Token 过期提前刷新时间 (秒)
    REFRESH_THRESHOLD = 300  # 提前5分钟刷新
    
    def __init__(self, client: 'BSHTClient'):
        self._client = client
        self._token_info: Optional[TokenInfo] = None
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._on_token_refreshed: Optional[Callable[[TokenInfo], None]] = None
    
    @property
    def access_token(self) -> Optional[str]:
        with self._lock:
            return self._token_info.access_token if self._token_info else None
    
    @property
    def token_info(self) -> Optional[TokenInfo]:
        with self._lock:
            return self._token_info
    
    def set_token(self, token_info: TokenInfo):
        """设置 Token 信息"""
        with self._lock:
            self._token_info = token_info
    
    def update_from_login(self, decoded: Dict[int, Any]) -> TokenInfo:
        """从登录响应更新 Token"""
        token_info = TokenInfo(
            access_token=decoded.get(1, ""),
            access_token_expires=decoded.get(2, 0),
            refresh_token=decoded.get(3, ""),
            refresh_token_expires=decoded.get(4, 0)
        )
        self.set_token(token_info)
        return token_info
    
    def is_expired(self) -> bool:
        """检查 Token 是否已过期"""
        if not self._token_info:
            return True
        return time.time() >= self._token_info.access_token_expires - self.REFRESH_THRESHOLD
    
    def start_auto_refresh(self):
        """启动自动刷新线程"""
        if self._refresh_thread and self._refresh_thread.is_alive():
            return
        
        self._stop_event.clear()
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()
    
    def stop_auto_refresh(self):
        """停止自动刷新"""
        self._stop_event.set()
        if self._refresh_thread:
            self._refresh_thread.join(timeout=5)
            self._refresh_thread = None
    
    def _refresh_loop(self):
        """自动刷新循环 - 增强版，刷新失败时重新登录"""
        consecutive_failures = 0  # 连续失败计数
        max_consecutive_failures = 3  # 最大连续失败次数

        while not self._stop_event.is_set():
            try:
                if self.is_expired() and self._token_info:
                    # 尝试刷新 Token
                    success = self._do_refresh()

                    if success:
                        # 刷新成功，重置失败计数
                        consecutive_failures = 0
                    else:
                        # 刷新失败
                        consecutive_failures += 1
                        logger.warning(f"⚠️ Token刷新失败 (连续失败 {consecutive_failures}/{max_consecutive_failures})")

                        # 检查是否需要重新登录
                        if consecutive_failures >= max_consecutive_failures:
                            logger.error("❌ Token刷新连续失败，尝试重新登录...")

                            # 调用客户端的重新登录方法
                            if hasattr(self._client, '_relogin'):
                                relogin_success = self._client._relogin()

                                if relogin_success:
                                    # 重新登录成功，重置失败计数
                                    consecutive_failures = 0
                                    logger.info("✅ 重新登录成功，Token已更新")
                                else:
                                    # 重新登录也失败了
                                    logger.error("❌ 重新登录失败，等待下次重试...")
                                    # 不重置计数器，下次继续尝试重新登录
                            else:
                                logger.error("❌ 客户端不支持重新登录")
                                consecutive_failures = 0  # 重置，避免一直报错

            except Exception as e:
                logger.error(f"❌ Token刷新循环异常: {e}")

            # 每30秒检查一次
            self._stop_event.wait(30)
    
    def _do_refresh(self) -> bool:
        """执行 Token 刷新"""
        if not self._token_info:
            return False
        
        try:
            # 构建刷新请求
            body = (
                ProtobufCodec.encode_string(1, self._token_info.access_token) +
                ProtobufCodec.encode_string(2, self._token_info.refresh_token)
            )
            
            message, trailers = self._client._grpc.request(
                "benshikj.User", "FreshAccessToken", body
            )
            
            if trailers.get('grpc-status') == '0' and message:
                decoded = ProtobufCodec.decode_message(message)
                new_token = TokenInfo(
                    access_token=decoded.get(1, ""),
                    access_token_expires=decoded.get(2, 0),
                    refresh_token=decoded.get(3, ""),
                    refresh_token_expires=decoded.get(4, 0)
                )
                self.set_token(new_token)
                
                # 回调通知
                if self._on_token_refreshed:
                    self._on_token_refreshed(new_token)
                
                return True
        except Exception as e:
            logger.warning(f"Token刷新失败: {e}")

        return False
    
    def force_refresh(self) -> bool:
        """强制刷新 Token"""
        return self._do_refresh()
    
    def set_on_refreshed(self, callback: Callable[[TokenInfo], None]):
        """设置 Token 刷新回调"""
        self._on_token_refreshed = callback
    
    def get_expires_in(self) -> int:
        """获取 Token 剩余有效时间 (秒)"""
        if not self._token_info:
            return 0
        remaining = self._token_info.access_token_expires - int(time.time())
        return max(0, remaining)
    
    def get_token_status(self) -> dict:
        """获取 Token 详细状态"""
        if not self._token_info:
            return {
                "has_token": False,
                "is_expired": True,
                "expires_in": 0,
            }
        
        now = int(time.time())
        access_expires_in = max(0, self._token_info.access_token_expires - now)
        refresh_expires_in = max(0, self._token_info.refresh_token_expires - now)
        
        return {
            "has_token": True,
            "is_expired": access_expires_in == 0,
            "needs_refresh": access_expires_in < self.REFRESH_THRESHOLD,
            "expires_in": access_expires_in,
            "refresh_expires_in": refresh_expires_in,
            "access_token_preview": self._token_info.access_token[:20] + "..." if self._token_info.access_token else "",
        }
    
    def to_dict(self) -> dict:
        """转换为字典用于保存"""
        if not self._token_info:
            return {}
        return {
            "access_token": self._token_info.access_token,
            "access_token_expires": self._token_info.access_token_expires,
            "refresh_token": self._token_info.refresh_token,
            "refresh_token_expires": self._token_info.refresh_token_expires,
        }
    
    def from_dict(self, data: dict):
        """从字典加载"""
        if data:
            self._token_info = TokenInfo(
                access_token=data.get("access_token", ""),
                access_token_expires=data.get("access_token_expires", 0),
                refresh_token=data.get("refresh_token", ""),
                refresh_token_expires=data.get("refresh_token_expires", 0),
            )


# ==================== API 响应封装 ====================

@dataclass
class ApiResponse:
    """API 响应封装"""
    success: bool
    data: Any = None
    error: str = ""
    error_code: int = 0
    
    @classmethod
    def ok(cls, data: Any = None) -> 'ApiResponse':
        return cls(success=True, data=data)
    
    @classmethod
    def error(cls, message: str, code: int = 0) -> 'ApiResponse':
        return cls(success=False, error=message, error_code=code)


# ==================== BSHT 主客户端 ====================

class BSHTClient:
    """
    BSHT 完整客户端
    
    功能:
    - 用户登录/登出
    - Token 自动刷新
    - 用户资料管理
    - 频道浏览/操作
    - 成员管理
    """
    
    def __init__(self, auto_refresh_token: bool = True):
        self._grpc = GrpcClient()
        self._token_manager = TokenManager(self)
        self._profile: Optional[UserProfile] = None

        # 保存登录凭据，用于Token刷新失败后重新登录
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        if auto_refresh_token:
            self._token_manager.start_auto_refresh()

    @property
    def token_manager(self) -> TokenManager:
        return self._token_manager
    
    # ==================== 认证相关 ====================
    
    def login(self, username: str, password: str) -> ApiResponse:
        """
        用户名密码登录

        Args:
            username: 用户名
            password: 密码

        Returns:
            ApiResponse with TokenInfo
        """
        # 保存凭据，用于后续自动重新登录
        self._username = username
        self._password = password

        body = (
            ProtobufCodec.encode_string(1, username) +
            ProtobufCodec.encode_string(2, password)
        )

        try:
            message, trailers = self._grpc.request(
                "benshikj.User", "Login", body
            )

            grpc_status = trailers.get('grpc-status', '-1')
            if grpc_status != '0':
                return ApiResponse.error(
                    f"登录失败: {trailers.get('grpc-message', 'Unknown error')}",
                    int(grpc_status)
                )

            if message:
                decoded = ProtobufCodec.decode_message(message)
                token_info = self._token_manager.update_from_login(decoded)
                return ApiResponse.ok(token_info)

            return ApiResponse.error("登录失败: 无响应数据")

        except Exception as e:
            return ApiResponse.error(f"登录请求失败: {e}")
    
    def login_with_token(self, access_token: str, refresh_token: str = "") -> ApiResponse:
        """
        使用已有 Token 登录
        
        Args:
            access_token: 访问令牌
            refresh_token: 刷新令牌 (可选)
            
        Returns:
            ApiResponse
        """
        # 设置 token
        token_info = TokenInfo(
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_expires=int(time.time()) + 3600,  # 假设1小时
            refresh_token_expires=int(time.time()) + 86400 * 7  # 假设7天
        )
        self._token_manager.set_token(token_info)
        
        # 验证 token 是否有效
        profile_result = self.load_profile()
        if profile_result.success:
            return ApiResponse.ok(token_info)
        else:
            self._token_manager.set_token(None)
            return ApiResponse.error("Token 无效或已过期")
    
    def logout(self) -> ApiResponse:
        """
        登出
        
        Returns:
            ApiResponse
        """
        token_info = self._token_manager.token_info
        if not token_info:
            return ApiResponse.ok()
        
        body = (
            ProtobufCodec.encode_string(1, token_info.access_token) +
            ProtobufCodec.encode_string(2, token_info.refresh_token)
        )
        
        try:
            message, trailers = self._grpc.request(
                "benshikj.User", "Logout", body,
                access_token=token_info.access_token
            )

            # 无论结果如何，都清除本地 token
            self._token_manager.set_token(None)

            if trailers.get('grpc-status') == '0':
                return ApiResponse.ok()
            else:
                return ApiResponse.error(f"登出失败: {trailers.get('grpc-message')}")

        except Exception as e:
            return ApiResponse.error(f"登出请求失败: {e}")

    def _relogin(self) -> bool:
        """
        内部方法：使用保存的凭据重新登录 (Token刷新失败时调用)

        Returns:
            是否重新登录成功
        """
        if not self._username or not self._password:
            logger.warning("❌ 无法重新登录：未保存用户凭据")
            return False

        logger.info(f"🔄 Token刷新失败，尝试使用保存的凭据重新登录...")

        # 重试3次
        for attempt in range(1, 4):
            try:
                # 等待一段时间再重试
                if attempt > 1:
                    time.sleep(5 * attempt)

                result = self.login(self._username, self._password)

                if result.success:
                    logger.info(f"✅ 重新登录成功 (尝试 {attempt}/3)")
                    # 保存新的凭证
                    self.save_credentials()
                    return True
                else:
                    logger.warning(f"⚠️ 重新登录失败 (尝试 {attempt}/3): {result.error}")

            except Exception as e:
                logger.error(f"❌ 重新登录异常 (尝试 {attempt}/3): {e}")

        logger.error("❌ 重新登录失败：已达到最大重试次数")
        return False
    
    @property
    def access_token(self) -> Optional[str]:
        """获取当前 access_token"""
        return self._token_manager.access_token
    
    @property
    def is_logged_in(self) -> bool:
        """检查是否已登录"""
        return self._token_manager.access_token is not None
    
    def set_token_refresh_callback(self, callback: Callable[[TokenInfo], None]):
        """设置 Token 刷新回调"""
        self._token_manager.set_on_refreshed(callback)
    
    # ==================== 用户资料 ====================
    
    def load_profile(self) -> ApiResponse:
        """
        加载用户资料
        
        Returns:
            ApiResponse with UserProfile
        """
        access_token = self.access_token
        if not access_token:
            return ApiResponse.error("请先登录", StatusCode.ERR_NOT_LOGIN)
        
        try:
            message, trailers = self._grpc.request(
                "benshikj.User", "LoadProfile", b'',
                access_token=access_token
            )
            
            if trailers.get('grpc-status') != '0':
                return ApiResponse.error(f"加载资料失败: {trailers.get('grpc-message')}")
            
            if message:
                decoded = ProtobufCodec.decode_message(message)
                
                # 解析嵌套的 profile 数据 (字段2)
                if 2 in decoded and isinstance(decoded[2], bytes):
                    profile_data = ProtobufCodec.decode_message(decoded[2])
                    self._profile = UserProfile(
                        user_id=profile_data.get(1, 0),
                        username=profile_data.get(2, ""),
                        nickname=profile_data.get(3, ""),
                        email=profile_data.get(4, ""),
                        photo=profile_data.get(5, b'') if isinstance(profile_data.get(5), bytes) else b'',
                        update_at=profile_data.get(6, 0)
                    )
                    return ApiResponse.ok(self._profile)
                
                return ApiResponse.error("解析资料失败")
            
            return ApiResponse.error("无响应数据")
            
        except Exception as e:
            return ApiResponse.error(f"加载资料失败: {e}")
    
    def get_user_info(self, user_id: int) -> ApiResponse:
        """
        获取指定用户信息
        """
        access_token = self.access_token
        if not access_token:
            return ApiResponse.error("请先登录", StatusCode.ERR_NOT_LOGIN)

        # 猜测: 字段1 为 user_id
        body = ProtobufCodec.encode_uint64(1, user_id)
        
        try:
            # 猜测 RPC 方法名: GetUserInfo
            message, trailers = self._grpc.request(
                "benshikj.User", "GetUserInfo", body,
                access_token=access_token
            )
            
            if trailers.get('grpc-status') != '0':
                return ApiResponse.error(f"获取用户信息失败: {trailers.get('grpc-message')}")

            if message:
                decoded = ProtobufCodec.decode_message(message)
                logger.debug(f"GetUserInfo({user_id}) response: {decoded}")

                profile = UserProfile(user_id=user_id)
                
                # 尝试解析
                # Case A: Response IS UserProfile
                if 3 in decoded and isinstance(decoded[3], str): # field 3 is nickname
                     profile.username = decoded.get(2, "")
                     profile.nickname = decoded.get(3, "")
                     profile.photo = decoded.get(5, b'')
                # Case B: Response contains UserProfile in field 1 or 2
                elif 1 in decoded and isinstance(decoded[1], bytes): # nested msg
                     nested = ProtobufCodec.decode_message(decoded[1])
                     if 3 in nested:
                         profile.user_id = nested.get(1, user_id)
                         profile.username = nested.get(2, "")
                         profile.nickname = nested.get(3, "")
                
                return ApiResponse.ok(profile)
            
            return ApiResponse.error("无响应数据")
        except Exception as e:
            return ApiResponse.error(f"Request failed: {e}")
    
    def update_profile(self, nickname: str = None, email: str = None) -> ApiResponse:
        """
        更新用户资料
        
        Args:
            nickname: 新昵称 (可选)
            email: 新邮箱 (可选)
            
        Returns:
            ApiResponse
        """
        access_token = self.access_token
        if not access_token:
            return ApiResponse.error("请先登录", StatusCode.ERR_NOT_LOGIN)
        
        # 构建 profile 消息
        profile_msg = b''
        update_flags = b''
        
        if nickname is not None:
            profile_msg += ProtobufCodec.encode_string(3, nickname)
            update_flags += ProtobufCodec.encode_bool(1, True)
        
        if email is not None:
            profile_msg += ProtobufCodec.encode_string(4, email)
            update_flags += ProtobufCodec.encode_bool(2, True) if email else b''
        
        if not profile_msg:
            return ApiResponse.error("没有要更新的内容")
        
        # 构建请求: {1: profile, 2: update_flags}
        body = (
            ProtobufCodec.encode_message(1, profile_msg) +
            ProtobufCodec.encode_message(2, update_flags)
        )
        
        try:
            message, trailers = self._grpc.request(
                "benshikj.User", "UpdateProfile", body,
                access_token=access_token
            )
            
            if trailers.get('grpc-status') == '0':
                # 更新本地缓存
                if self._profile:
                    if nickname:
                        self._profile.nickname = nickname
                    if email:
                        self._profile.email = email
                return ApiResponse.ok()
            else:
                return ApiResponse.error(f"更新资料失败: {trailers.get('grpc-message')}")
                
        except Exception as e:
            return ApiResponse.error(f"更新资料失败: {e}")
    
    @property
    def profile(self) -> Optional[UserProfile]:
        """获取缓存的用户资料"""
        return self._profile
    
    # ==================== 频道浏览 ====================
    
    def search_channels(self, query: str = "", offset: int = 0, limit: int = 50) -> ApiResponse:
        """
        搜索频道
        
        Args:
            query: 搜索关键词
            offset: 偏移量
            limit: 返回数量
            
        Returns:
            ApiResponse with List[ChannelInfo]
        """
        access_token = self.access_token
        if not access_token:
            return ApiResponse.error("请先登录", StatusCode.ERR_NOT_LOGIN)
        
        body = (
            ProtobufCodec.encode_string(1, query) +
            ProtobufCodec.encode_int32(2, offset) +
            ProtobufCodec.encode_int32(3, limit)
        )
        
        try:
            message, trailers = self._grpc.request(
                "benshikj.IHT", "GetChannels", body,
                access_token=access_token
            )
            
            if trailers.get('grpc-status') != '0':
                return ApiResponse.error(f"搜索频道失败: {trailers.get('grpc-message')}")
            
            if message:
                decoded = ProtobufCodec.decode_message(message)
                channels = []
                
                # 字段1 是 repeated IIChannel
                if 1 in decoded:
                    channels = self._parse_repeated_channels(decoded[1])
                
                return ApiResponse.ok(channels)
            
            return ApiResponse.ok([])
            
        except Exception as e:
            return ApiResponse.error(f"搜索频道失败: {e}")
    
    def _parse_repeated_channels(self, data: bytes) -> List[ChannelInfo]:
        """解析 repeated Channel 数据"""
        channels = []
        
        # data 可能是单个 bytes 或 list of bytes
        if isinstance(data, list):
            items = data
        else:
            items = [data]
        
        for item in items:
            if isinstance(item, bytes):
                channel_fields = ProtobufCodec.decode_message(item)
                channels.append(ChannelInfo(
                    channel_id=channel_fields.get(1, 0),
                    name=channel_fields.get(2, ""),
                    has_passcode=channel_fields.get(3, False),
                    user_count=channel_fields.get(4, 0)
                ))
        
        return channels
    
    def get_user_channels(self, offset: int = 0, limit: int = 50) -> ApiResponse:
        """
        获取用户加入的频道
        
        Args:
            offset: 偏移量
            limit: 返回数量
            
        Returns:
            ApiResponse with List[UserChannel]
        """
        access_token = self.access_token
        if not access_token:
            return ApiResponse.error("请先登录", StatusCode.ERR_NOT_LOGIN)
        
        body = (
            ProtobufCodec.encode_int32(1, offset) +
            ProtobufCodec.encode_int32(2, limit)
        )
        
        try:
            message, trailers = self._grpc.request(
                "benshikj.IHT", "GetUserChannels", body,
                access_token=access_token
            )
            
            if trailers.get('grpc-status') != '0':
                return ApiResponse.error(f"获取频道失败: {trailers.get('grpc-message')}")
            
            if message:
                decoded = ProtobufCodec.decode_message(message)
                channels = []
                
                # 字段1 是 repeated UserChannel
                if 1 in decoded:
                    channels = self._parse_user_channels(decoded[1])
                
                return ApiResponse.ok(channels)
            
            return ApiResponse.ok([])
            
        except Exception as e:
            return ApiResponse.error(f"获取频道失败: {e}")
    
    def _parse_user_channels(self, data: bytes) -> List[UserChannel]:
        """解析用户频道数据"""
        channels = []
        
        # data 可能是单个 bytes 或 list of bytes
        if isinstance(data, list):
            items = data
        else:
            items = [data]
        
        for item in items:
            if not isinstance(item, bytes):
                continue
                
            fields = ProtobufCodec.decode_message(item)
            
            # 解析 auth 字段 (字段4)
            auth = {'ban': False, 'isAdmin': False, 'callPriority': 0}
            if 4 in fields and isinstance(fields[4], bytes):
                auth_fields = ProtobufCodec.decode_message(fields[4])
                auth = {
                    'ban': auth_fields.get(1, False),
                    'isAdmin': auth_fields.get(2, False),
                    'callPriority': auth_fields.get(3, 0)
                }
            
            # 解析 rf 配置 (字段5)
            rf_config = {}
            if 5 in fields and isinstance(fields[5], bytes):
                rf_fields = ProtobufCodec.decode_message(fields[5])
                rf_config = {
                    'txFreq': rf_fields.get(1, 0),
                    'rxFreq': rf_fields.get(2, 0),
                    'txSubAudio': rf_fields.get(3, 0),
                    'rxSubAudio': rf_fields.get(4, 0),
                    'bandwidth': rf_fields.get(5, 0)
                }
            
            channels.append(UserChannel(
                own_user_id=fields.get(1, 0),
                channel_id=fields.get(2, 0),
                name=fields.get(3, ""),
                is_banned=auth['ban'],
                is_admin=auth['isAdmin'],
                call_priority=auth['callPriority'],
                rf_config=rf_config
            ))
        
        return channels
    
    # ==================== 频道操作 ====================
    
    def join_channel(self, channel_id: int, passcode: int = 0) -> ApiResponse:
        """
        加入频道
        
        Args:
            channel_id: 频道 ID
            passcode: 频道密码 (如不需要则填 0)
            
        Returns:
            ApiResponse
        """
        access_token = self.access_token
        if not access_token:
            return ApiResponse.error("请先登录", StatusCode.ERR_NOT_LOGIN)
        
        body = (
            ProtobufCodec.encode_uint64(1, channel_id) +
            ProtobufCodec.encode_int32(2, passcode)
        )
        
        try:
            message, trailers = self._grpc.request(
                "benshikj.IHT", "JoinChannel", body,
                access_token=access_token
            )
            
            # JoinChannel 返回空消息，只要 gRPC status 为 0 就算成功
            grpc_status = trailers.get('grpc-status', '0')
            if grpc_status == '0':
                return ApiResponse.ok()
            else:
                return ApiResponse.error(f"加入频道失败: {trailers.get('grpc-message', 'Unknown error')}")
                
        except Exception as e:
            return ApiResponse.error(f"加入频道失败: {e}")
    
    def quit_channel(self, channel_id: int) -> ApiResponse:
        """
        退出频道
        
        Args:
            channel_id: 频道 ID
            
        Returns:
            ApiResponse
        """
        access_token = self.access_token
        if not access_token:
            return ApiResponse.error("请先登录", StatusCode.ERR_NOT_LOGIN)
        
        body = ProtobufCodec.encode_uint64(1, channel_id)
        
        try:
            message, trailers = self._grpc.request(
                "benshikj.IHT", "QuitChannel", body,
                access_token=access_token
            )
            
            # QuitChannel 返回空消息
            grpc_status = trailers.get('grpc-status', '0')
            if grpc_status == '0':
                return ApiResponse.ok()
            else:
                return ApiResponse.error(f"退出频道失败: {trailers.get('grpc-message', 'Unknown error')}")
                
        except Exception as e:
            return ApiResponse.error(f"退出频道失败: {e}")
    
    def get_channel_status(self, channel_id: int, update_at: int = 0) -> ApiResponse:
        """
        获取频道状态 (在线用户)
        
        Args:
            channel_id: 频道 ID
            update_at: 缓存时间戳 (用于增量更新)
            
        Returns:
            ApiResponse with {online_users: List[int], update_at: int}
        """
        access_token = self.access_token
        if not access_token:
            return ApiResponse.error("请先登录", StatusCode.ERR_NOT_LOGIN)
        
        body = (
            ProtobufCodec.encode_uint64(1, channel_id) +
            ProtobufCodec.encode_int32(2, update_at)
        )
        
        try:
            message, trailers = self._grpc.request(
                "benshikj.IHT", "GetChannelStatus", body,
                access_token=access_token
            )
            
            if trailers.get('grpc-status') != '0':
                return ApiResponse.error(f"获取状态失败: {trailers.get('grpc-message')}")
            
            if message:
                decoded = ProtobufCodec.decode_message(message)
                
                # 解析在线用户列表 (字段1是 repeated int64)
                online_users = []
                if 1 in decoded:
                    if isinstance(decoded[1], bytes):
                        # 解析 packed repeated int64
                        online_users = self._parse_packed_int64(decoded[1])
                    elif isinstance(decoded[1], int):
                        online_users = [decoded[1]]
                
                return ApiResponse.ok({
                    'online_users': online_users,
                    'update_at': decoded.get(2, 0)
                })
            
            return ApiResponse.ok({'online_users': [], 'update_at': 0})
            
        except Exception as e:
            return ApiResponse.error(f"获取状态失败: {e}")
    
    def _parse_packed_int64(self, data: bytes) -> List[int]:
        """解析 packed repeated int64"""
        result = []
        pos = 0
        while pos < len(data):
            value, pos = ProtobufCodec.decode_varint(data, pos)
            result.append(value)
        return result
    
    # ==================== 成员管理 ====================
    
    def get_channel_members(self, channel_id: int) -> ApiResponse:
        """
        获取频道成员列表
        
        Args:
            channel_id: 频道 ID
            
        Returns:
            ApiResponse with {own_user_id: int, members: List[ChannelMember]}
        """
        access_token = self.access_token
        if not access_token:
            return ApiResponse.error("请先登录", StatusCode.ERR_NOT_LOGIN)
        
        body = ProtobufCodec.encode_uint64(1, channel_id)
        
        try:
            message, trailers = self._grpc.request(
                "benshikj.IHT", "GetChannelMembers", body,
                access_token=access_token
            )
            
            if trailers.get('grpc-status') != '0':
                return ApiResponse.error(f"获取成员失败: {trailers.get('grpc-message')}")
            
            if message:
                decoded = ProtobufCodec.decode_message(message)
                logger.debug(f"GetChannelMembers response: {decoded}")

            own_user_id = decoded.get(1, 0)
            members = []
            
            # 字段2 是 repeated ChannelMember
            raw_members = decoded.get(2, [])
            if isinstance(raw_members, bytes):
                raw_members = [raw_members]
            elif not isinstance(raw_members, list):
                raw_members = []
                
            for member_data in raw_members:
                try:
                    m_fields = ProtobufCodec.decode_message(member_data)
                    members.append(ChannelMember(
                        user_id=m_fields.get(1, 0),
                        is_banned=m_fields.get(2, False),
                        is_admin=m_fields.get(3, False),
                        call_priority=m_fields.get(4, 0)
                    ))
                except Exception as e:
                    logger.debug(f"Failed to parse member: {e}")
            
            return ApiResponse.ok({
                'own_user_id': own_user_id,
                'members': members
            })
            
            return ApiResponse.ok({'own_user_id': 0, 'members': []})
            
        except Exception as e:
            return ApiResponse.error(f"获取成员失败: {e}")
    
    def _parse_channel_members(self, data: bytes) -> List[ChannelMember]:
        """解析频道成员数据"""
        members = []
        pos = 0
        
        while pos < len(data):
            if pos >= len(data):
                break
            tag = data[pos]
            pos += 1
            
            wire_type = tag & 0x07
            if wire_type == 2:
                length, pos = ProtobufCodec.decode_varint(data, pos)
                member_data = data[pos:pos + length]
                pos += length
                
                fields = ProtobufCodec.decode_message(member_data)
                members.append(ChannelMember(
                    user_id=fields.get(1, 0),
                    is_banned=fields.get(2, False),
                    is_admin=fields.get(3, False),
                    call_priority=fields.get(4, 0)
                ))
            else:
                break
        
        return members
    
    # ==================== 语音连接 ====================
    
    def get_channel_connection_params(self, channel_id: int) -> ApiResponse:
        """
        获取频道语音连接参数
        
        Args:
            channel_id: 频道 ID
            
        Returns:
            ApiResponse with ChannelConnectionParams
        """
        access_token = self.access_token
        if not access_token:
            return ApiResponse.error("请先登录", StatusCode.ERR_NOT_LOGIN)
        
        body = ProtobufCodec.encode_uint64(1, channel_id)
        
        try:
            message, trailers = self._grpc.request(
                "benshikj.IHT", "GetChannelConnectionParm", body,
                access_token=access_token
            )
            
            if trailers.get('grpc-status') != '0':
                return ApiResponse.error(f"获取语音参数失败: {trailers.get('grpc-message')}")
            
            if message:
                decoded = ProtobufCodec.decode_message(message)
                
                # 解析 auth 字段 (字段5)
                auth = {'ban': False, 'isAdmin': False, 'callPriority': 0}
                if 5 in decoded and isinstance(decoded[5], bytes):
                    auth_fields = ProtobufCodec.decode_message(decoded[5])
                    auth = {
                        'ban': auth_fields.get(1, False),
                        'isAdmin': auth_fields.get(2, False),
                        'callPriority': auth_fields.get(3, 0)
                    }
                
                # 解析 rf 配置 (字段6)
                rf_config = {}
                if 6 in decoded and isinstance(decoded[6], bytes):
                    rf_fields = ProtobufCodec.decode_message(decoded[6])
                    rf_config = {
                        'txFreq': rf_fields.get(1, 0),
                        'rxFreq': rf_fields.get(2, 0),
                        'txSubAudio': rf_fields.get(3, 0),
                        'rxSubAudio': rf_fields.get(4, 0),
                        'bandwidth': rf_fields.get(5, 0)
                    }
                
                params = ChannelConnectionParams(
                    ip=decoded.get(2, ""),
                    port=decoded.get(3, 0),
                    bit_rates=decoded.get(4, 0),
                    is_banned=auth['ban'],
                    is_admin=auth['isAdmin'],
                    call_priority=auth['callPriority'],
                    rf_config=rf_config
                )
                
                return ApiResponse.ok(params)
            
            return ApiResponse.error("无响应数据")
            
        except Exception as e:
            return ApiResponse.error(f"获取语音参数失败: {e}")
    
    def get_token_status(self) -> dict:
        """
        获取 Token 状态信息
        
        Returns:
            Token 状态字典
        """
        return self._token_manager.get_token_status()
    
    def force_refresh_token(self) -> bool:
        """
        强制刷新 Token
        
        Returns:
            是否刷新成功
        """
        return self._token_manager.force_refresh()
    
    # ==================== 工具方法 ====================
    
    def save_credentials(self, filepath: str = "credentials.json") -> bool:
        """保存凭证到文件"""
        try:
            data = {
                "token": self._token_manager.to_dict(),
                "profile": {
                    "user_id": self._profile.user_id if self._profile else 0,
                    "username": self._profile.username if self._profile else "",
                    "nickname": self._profile.nickname if self._profile else "",
                    "email": self._profile.email if self._profile else "",
                }
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.warning(f"保存凭证失败: {e}")
            return False

    def load_credentials(self, filepath: str = "credentials.json") -> bool:
        """从文件加载凭证"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "token" in data:
                self._token_manager.from_dict(data["token"])

            if "profile" in data:
                self._profile = UserProfile(**data["profile"])

            return True
        except Exception as e:
            logger.debug(f"加载凭证失败: {e}")
            return False
    
    def close(self):
        """关闭客户端"""
        self._token_manager.stop_auto_refresh()
        self._grpc.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ==================== 音频流监听器 ====================

class AudioStreamListener:
    """
    音频流监听器

    用于接收指定频道的实时音频数据

    协议说明:
    - 语音服务器通过 UDP 或 WebSocket 传输音频
    - 音频格式通常是 Opus 或 PCM
    - 需要先通过 GetChannelConnectionParm 获取服务器地址
    """

    def __init__(self, client: BSHTClient, enable_playback: bool = False):
        self._client = client
        self._socket = None
        self._is_listening = False
        self._listen_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 是否启用音频播放（需要声卡）
        self.enable_playback = enable_playback

        # 回调函数
        self._on_audio_frame: Optional[Callable[[AudioFrame], None]] = None
        self._on_user_speaking: Optional[Callable[[int, bool], None]] = None  # (user_id, is_speaking)
        self._on_error: Optional[Callable[[str], None]] = None

        # 当前连接信息
        self._channel_id: int = 0
        self._server_ip: str = ""
        self._server_port: int = 0

        # 发射状态锁 - 保护 _is_transmitting 标志的线程安全
        self._transmit_lock = threading.Lock()

        # ========== 重连机制参数 ==========
        self._reconnect_attempts = 0          # 当前重连尝试次数
        self._max_reconnect_attempts = 10     # 最大重连次数 (0=无限重连)
        self._reconnect_delay_base = 2        # 重连延迟基数(秒)
        self._reconnect_delay_max = 60        # 最大重连延迟(秒)
        self._last_packet_time = 0            # 最后收到数据包时间
        self._packet_timeout = 90             # 数据包超时时间(秒) - 心跳15s*6
        self._is_reconnecting = False         # 是否正在重连中

        # ========== 心跳状态统计 ==========
        self._heartbeat_count = 0            # 已发送心跳包数量
        self._heartbeat_last_report_time = 0  # 上次报告心跳状态的时间
        self._heartbeat_start_time = 0        # 心跳开始时间

    @property
    def is_listening(self) -> bool:
        return self._is_listening
    
    @property
    def channel_id(self) -> int:
        return self._channel_id
    
    def set_callbacks(self, 
                      on_audio_frame: Callable[[AudioFrame], None] = None,
                      on_user_speaking: Callable[[int, bool], None] = None,
                      on_error: Callable[[str], None] = None):
        """设置回调函数"""
        self._on_audio_frame = on_audio_frame
        self._on_user_speaking = on_user_speaking
        self._on_error = on_error
    
    def connect(self, channel_id: int) -> ApiResponse:
        """
        连接到频道的语音服务器
        
        Args:
            channel_id: 频道 ID
            
        Returns:
            ApiResponse
        """
        # 获取语音服务器参数
        result = self._client.get_channel_connection_params(channel_id)
        if not result.success:
            return result
        
        params: ChannelConnectionParams = result.data
        
        if not params.ip or not params.port:
            return ApiResponse.error("语音服务器地址无效")
        
        self._channel_id = channel_id
        self._server_ip = params.ip
        self._server_port = params.port
        
        return ApiResponse.ok({
            "ip": params.ip,
            "port": params.port,
            "bit_rates": params.bit_rates,
            "is_admin": params.is_admin,
            "call_priority": params.call_priority,
        })
    
    def start_listening(self) -> bool:
        """
        开始监听音频流

        Returns:
            是否成功启动
        """
        if self._is_listening:
            return True

        if not self._server_ip or not self._server_port:
            if self._on_error:
                self._on_error("请先调用 connect() 连接到语音服务器")
            return False

        try:
            import socket

            # 创建 UDP socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.settimeout(1.0)  # 1秒超时

            # 增大 UDP 接收缓冲区 (默认 8KB → 512KB)
            # 减少网络突发、GIL 阻塞时 OS 层丢帧
            try:
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 512 * 1024)
            except Exception:
                pass

            # 绑定本地端口
            self._socket.bind(('0.0.0.0', 0))
            local_port = self._socket.getsockname()[1]

            # 发送注册包到语音服务器
            # 注意: 实际的协议格式需要进一步分析
            # 这里先发送一个简单的标识包
            register_packet = self._build_register_packet()
            self._socket.sendto(register_packet, (self._server_ip, self._server_port))

            # 初始化重连状态
            self._last_packet_time = time.time()
            self._reconnect_attempts = 0
            self._is_reconnecting = False

            # 启动监听线程
            self._stop_event.clear()
            self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._listen_thread.start()

            # 启动心跳线程
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()

            self._is_listening = True
            return True

        except Exception as e:
            if self._on_error:
                self._on_error(f"启动监听失败: {e}")
            return False
    
    def stop_listening(self):
        """停止监听"""
        self._is_listening = False
        self._stop_event.set()
        
        if self._socket:
            try:
                self._socket.close()
            except (OSError, AttributeError) as e:
                # 忽略 socket 关闭错误
                pass
            self._socket = None
        
        if self._listen_thread:
            self._listen_thread.join(timeout=3)
            self._listen_thread = None

        if hasattr(self, '_heartbeat_thread') and self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=1)
            self._heartbeat_thread = None
    
    def _build_register_packet(self) -> bytes:
        """
        构建 UDP 注册包 (使用 Binary Protocol)
        """
        user_id = self._client.profile.user_id if self._client.profile else 0
        token = self._client.token_manager.access_token if self._client.token_manager else ""
        
        packet = BinaryPacket.create_login_packet(user_id, token)
        return packet.to_bytes()

    def _heartbeat_loop(self):
        """心跳线程 (模拟) - 带定期状态报告"""
        # 初始化心跳开始时间
        import time as time_module
        self._heartbeat_start_time = time_module.time()
        self._heartbeat_last_report_time = self._heartbeat_start_time

        report_interval = 300  # 5分钟报告一次 (15秒*20=300秒)

        while not self._stop_event.is_set():
            try:
                # 发送心跳包
                heartbeat = self._build_heartbeat_packet()
                if self._socket:
                    # DEBUG 级别：每次心跳都记录
                    logger.debug(f"发送心跳 ({len(heartbeat)} 字节)")
                    self._socket.sendto(heartbeat, (self._server_ip, self._server_port))

                    # 增加心跳计数
                    self._heartbeat_count += 1

                    # 定期报告心跳状态 (INFO 级别)
                    current_time = time_module.time()
                    if current_time - self._heartbeat_last_report_time >= report_interval:
                        # 计算心跳持续时间
                        elapsed = current_time - self._heartbeat_start_time
                        hours = int(elapsed // 3600)
                        minutes = int((elapsed % 3600) // 60)

                        if hours > 0:
                            time_str = f"{hours}小时{minutes}分钟"
                        else:
                            time_str = f"{minutes}分钟"

                        logger.info(f"[心跳] 💓 心跳正常 - 已运行 {time_str}, "
                                   f"发送 {self._heartbeat_count} 个心跳包 (15秒/次)")

                        # 重置报告计时器
                        self._heartbeat_last_report_time = current_time

                time_module.sleep(15)  # 15秒心跳一次
            except Exception as e:
                logger.warning(f"心跳发送失败: {e}")
                time_module.sleep(5)
    
    def _listen_loop(self):
        """
        监听循环 (接收线程) - 带自动重连机制

        RTP包 → AudioMixer (per-user JitterBuffer) → 播放线程
        """
        import socket
        # 先导入 AudioMixer（不依赖 pyaudio）
        from audio_mixer import AudioMixer

        try:
            # 根据配置决定是否初始化音频播放
            if self.enable_playback:
                try:
                    import pyaudio
                except ImportError:
                    logger.warning("PyAudio 未安装，播放已禁用")
                    raise

                # 初始化音频输出 (增大缓冲区避免 underrun)
                p = pyaudio.PyAudio()
                stream = None
                try:
                    stream = p.open(format=pyaudio.paInt16,
                                    channels=1,
                                    rate=48000,
                                    output=True,
                                    frames_per_buffer=4096)  # ~85ms 缓冲
                    logger.info("音频播放已启动 (Opus 48kHz, 多用户混音)")
                except Exception as e:
                    logger.warning(f"音频初始化失败: {e}")
                    logger.info("运行在无声卡模式 (仅录制，不播放)")
                    p = None
                    stream = None
            else:
                # 不启用播放，不需要导入 pyaudio
                p = None
                stream = None
                logger.info("🔇 无播放模式：仅录制+识别+推送")

            # 创建多用户混音器 (替代单个 JitterBuffer + Decoder)
            mixer = AudioMixer()
            self._mixer = mixer  # 保存引用，外部可设置昵称

            # === 预热 Opus 解码器 DLL (消除首次 RX 丢包) ===
            try:
                from audio_codec import OpusDecoder as _WarmupDecoder
                _warmup = _WarmupDecoder(48000, 1)
                _warmup.destroy()
                del _warmup
                logger.info("Opus 解码器 DLL 预加载完成")
            except Exception as e:
                logger.warning(f"Opus 解码器预热失败(非致命): {e}")

            # === 预初始化 TX 组件 (消除首次PTT延迟) ===
            try:
                from audio_codec import OpusEncoder, SAMPLE_RATE, FRAME_SIZE
                if not hasattr(self, '_tx_encoder') or self._tx_encoder is None:
                    self._tx_encoder = OpusEncoder(
                        sample_rate=SAMPLE_RATE,
                        frame_size=FRAME_SIZE,
                        bitrate=32000
                    )
                    logger.debug("Opus编码器预热完成")

                # 本地麦克风录音器: 仅在 enable_local_mic=True 时预初始化
                if getattr(self, 'enable_local_mic', False) and stream is not None:
                    from audio_codec import AudioRecorder
                    if not hasattr(self, '_tx_recorder') or self._tx_recorder is None:
                        self._tx_recorder = AudioRecorder(
                            sample_rate=SAMPLE_RATE,
                            frame_size=FRAME_SIZE,
                            channels=1
                        )
                        self._tx_recorder.start_recording()
                        logger.info("录音器预热完成 (本地麦克风已就绪)")
                else:
                    logger.info("本地麦克风未启用 (Web PTT 模式)")

            except Exception as e:
                logger.warning(f"TX预初始化失败(非致命): {e}")
        except Exception as e:
            logger.error(f"音频初始化失败: {e}")
            p = None
            stream = None
            mixer = None

        # 启动独立播放线程 (即使无声卡也要运行，用于驱动录制逻辑)
        playback_stop = threading.Event()
        if mixer:
            playback_thread = threading.Thread(
                target=self._playback_loop,
                args=(mixer, stream, playback_stop),
                daemon=True
            )
            playback_thread.start()
        else:
            playback_thread = None

        # ========== 外层循环：处理重连 ==========
        while not self._stop_event.is_set():
            if self._is_reconnecting:
                # 避免多个线程同时重连
                time.sleep(1)
                continue

            try:
                # ========== 内层监听循环 ==========
                while not self._stop_event.is_set() and self._socket:
                    # 设置socket超时，用于定期检查重连条件
                    self._socket.settimeout(5.0)

                    try:
                        data, addr = self._socket.recvfrom(4096)

                        # 更新最后接收时间
                        self._last_packet_time = time.time()
                        # 重连成功，重置计数器
                        self._reconnect_attempts = 0

                        # 尝试解析为 RTP 包
                        try:
                            if len(data) >= 12:
                                rtp_pkt = RTPPacket.parse(data)

                                # 检测 RX_AUDIO_STOP: 空 payload
                                if not rtp_pkt.payload or len(rtp_pkt.payload) == 0:
                                    self._process_audio_data(
                                        b'',
                                        user_id=rtp_pkt.ssrc,
                                        sequence=rtp_pkt.sequence_number,
                                        marker=bool(rtp_pkt.marker),
                                        is_stop=True
                                    )
                                    continue

                                # 正常音频帧 → 放入混音器
                                if mixer:
                                    mixer.push(
                                        ssrc=rtp_pkt.ssrc,
                                        sequence=rtp_pkt.sequence_number,
                                        opus_data=rtp_pkt.payload,
                                        marker=bool(rtp_pkt.marker)
                                    )

                                # 回调通知 (说话者检测等)
                                self._process_audio_data(
                                    rtp_pkt.payload,
                                    user_id=rtp_pkt.ssrc,
                                    sequence=rtp_pkt.sequence_number,
                                    marker=bool(rtp_pkt.marker)
                                )
                                continue
                        except Exception as e:
                            logger.debug(f"RTP包处理异常: {e}")

                    except socket.timeout:
                        # 超时正常，检查是否需要重连
                        current_time = time.time()
                        if self._last_packet_time > 0 and (current_time - self._last_packet_time) > self._packet_timeout:
                            logger.warning(f"⚠️ {int(current_time - self._last_packet_time)}秒未收到数据包，触发重连")
                            break  # 跳出内层循环，触发重连
                        continue

                    except Exception as e:
                        # 其他异常，触发重连
                        logger.error(f"❌ 接收异常: {e}")
                        break  # 跳出内层循环，触发重连

                # ========== 内层循环退出，检查是否需要重连 ==========
                if self._stop_event.is_set():
                    logger.info("监听线程收到停止信号")
                    break

                # 如果socket被清理了，说明需要重连
                if not self._socket:
                    logger.warning("Socket已关闭，尝试重连...")
                    if not self._do_reconnect():
                        logger.error("重连失败，退出监听线程")
                        break
                    continue  # 重连成功，继续外层循环

            except Exception as e:
                logger.error(f"❌ 监听循环严重错误: {e}")
                # 尝试重连
                if not self._do_reconnect():
                    logger.error("重连失败，退出监听线程")
                    break

        # ========== 清理 ==========
        logger.info("监听线程退出")
        self._is_listening = False

        playback_stop.set()
        if playback_thread:
            playback_thread.join(timeout=2)
        if stream:
            stream.stop_stream()
            stream.close()
        if p and hasattr(p, 'terminate'):
            p.terminate()

        if hasattr(self, '_mixer') and self._mixer:
            self._mixer.shutdown()

    def _do_reconnect(self) -> bool:
        """
        执行重连逻辑 (指数退避)

        Returns:
            是否重连成功
        """
        if self._is_reconnecting:
            return False

        # 检查重连次数限制
        if self._max_reconnect_attempts > 0 and self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(f"❌ 已达到最大重连次数 ({self._max_reconnect_attempts})，停止重试")
            return False

        self._is_reconnecting = True
        self._reconnect_attempts += 1

        # 计算退避延迟
        delay = min(
            self._reconnect_delay_max,
            self._reconnect_delay_base ** self._reconnect_attempts
        )
        # 至少等待2秒
        delay = max(2, delay)

        logger.info(f"🔄 等待 {delay:.1f} 秒后重连... (尝试 {self._reconnect_attempts}/{self._max_reconnect_attempts if self._max_reconnect_attempts > 0 else '∞'})")

        # 清理旧资源
        try:
            if self._socket:
                self._socket.close()
                self._socket = None
        except Exception:
            pass

        time.sleep(delay)

        # 重新连接
        try:
            import socket

            # 创建新socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.settimeout(1.0)

            # 增大接收缓冲区
            try:
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 512 * 1024)
            except Exception:
                pass

            # 绑定本地端口
            self._socket.bind(('0.0.0.0', 0))

            # 发送注册包
            register_packet = self._build_register_packet()
            self._socket.sendto(register_packet, (self._server_ip, self._server_port))

            self._last_packet_time = time.time()
            self._is_reconnecting = False

            logger.info(f"✅ 重连成功: {self._server_ip}:{self._server_port}")
            return True

        except Exception as e:
            logger.error(f"❌ 重连失败: {e}")
            self._is_reconnecting = False
            return False

    def _playback_loop(self, mixer, stream, stop_event):
        """
        独立播放线程: 从 AudioMixer 取混音后的 PCM → 播放
        
        关键设计: 不使用 time.sleep() 控制节奏!
        stream.write(pcm) 本身就是阻塞的 (PyAudio 会等内部 buffer 有空间)
        960 samples @ 48kHz = 20ms, write 自然阻塞 ~20ms
        """
        import time
        
        FRAME_SIZE = 960
        silence_pcm = b'\x00' * (FRAME_SIZE * 2)
        cleanup_counter = 0
        was_idle = True  # 追踪是否从静默状态转换
        
        while not stop_event.is_set():
            
            if not mixer.has_active_speakers:
                # 无人说话，低频轮询
                time.sleep(0.005)
                was_idle = True
                
                # 定期清理过期用户流
                cleanup_counter += 1
                if cleanup_counter > 200:  # ~1秒
                    mixer.cleanup_expired()
                    cleanup_counter = 0
                continue
            
            # === 从静默→有人说话: 预填充 PyAudio 输出缓冲区 ===
            # 长时间沉默后输出缓冲区为空，stream.write() 不阻塞
            # 导致 pop_mixed() 被极速调用，JitterBuffer 被瞬间清空
            # 预写静音帧填满缓冲区，确保后续 write 正常阻塞 ~20ms
            if was_idle and stream:
                try:
                    for _ in range(4):  # 4帧 × 960 = 3840 samples ≈ 填满 4096 buffer
                        stream.write(silence_pcm)
                except Exception:
                    pass
                was_idle = False
            
            # 从混音器取混合后的 PCM
            pcm = mixer.pop_mixed()
            
            if pcm is not None:
                if stream:
                    try:
                        stream.write(pcm)  # 阻塞 ~20ms, 自然控制节拍
                    except Exception as e:
                        logger.debug(f"播放PCM数据失败: {e}")
                else:
                    time.sleep(0.018) # 无声卡模拟阻塞
            else:
                # 混音器返回 None (所有用户缓冲为空)
                if stream:
                    try:
                        stream.write(silence_pcm)
                    except Exception as e:
                        logger.debug(f"播放静音数据失败: {e}")
                else:
                    time.sleep(0.018)

    def _process_audio_data(self, data: bytes, user_id: int = 0, sequence: int = 0, marker: bool = False, is_stop: bool = False):
        """
        处理接收到的 UDP 数据包
        
        Args:
            data: 音频数据 payload
            user_id: 发送者用户 ID (从 RTP SSRC 获取)
            sequence: 序列号
            marker: 是否为 Marker 位 (关键帧/PTT开始)
            is_stop: 是否为停止包 (RX_AUDIO_STOP)
        """
        # 如果有回调，直接构造 AudioFrame 并回调
        if self._on_audio_frame:
             self._on_audio_frame(AudioFrame(user_id=user_id, data=data, sequence=sequence, end_marker=marker, is_stop=is_stop))
             return

        # 旧逻辑保留 (BinaryPacket解析) - 实际上 _listen_loop 已经拦截了 RTP
        try:
            # 临时补丁: 忽略非常短的包，避免解析错误
            if len(data) < 2:
                return

            packet = HTPacket.parse(data)
            
            if isinstance(packet, BinaryPacket):
                # 处理二进制协议 (语音/信令)
                if Tag.CHANNEL in packet.tags:
                    # 获取语音数据 payload
                    audio_payload = packet.tags[Tag.CHANNEL]
                    if self._on_audio_frame:
                         self._on_audio_frame(AudioFrame(user_id=0, data=audio_payload))
                elif Tag.MESSAGE in packet.tags:
                    logger.info(f"收到UDP消息: {packet.tags[Tag.MESSAGE]}")

            elif isinstance(packet, AX25Packet):
                # 处理 AX.25 协议 (APRS/心跳)
                logger.debug(f"收到 AX.25 包: Src={packet.source}, Dst={packet.destination}")
                pass

        except ProtocolError:
            pass # 忽略解析错误
        except Exception as e:
            logger.debug(f"UDP处理异常: {e}")
    
    def send_audio(self, audio_data: bytes, marker: bool = False) -> bool:
        """
        发送音频数据 (说话)
        
        Args:
            audio_data: Opus 编码后的音频数据
            marker: 是否设置 Marker 位 (首包)
            
        Returns:
            是否发送成功
        """
        if not self._socket or not self._is_listening:
            return False
        
        try:
            # 封装音频数据包
            packet = self._build_audio_packet(audio_data, marker=marker)
            self._socket.sendto(packet, (self._server_ip, self._server_port))
            return True
        except Exception as e:
            if self._on_error:
                self._on_error(f"发送音频失败: {e}")
            return False
    
    def _build_audio_packet(self, audio_data: bytes, marker: bool = False) -> bytes:
        """
        构建音频数据包 (RTP)
        """
        if not hasattr(self, '_rtp_seq'):
            self._rtp_seq = 0
            self._rtp_ts = 0
            
        self._rtp_seq = (self._rtp_seq + 1) & 0xFFFF
        self._rtp_ts = (self._rtp_ts + 960) & 0xFFFFFFFF # 20ms frame @ 48kHz
        
        user_id = self._client.profile.user_id if self._client.profile else 0
        pkt = RTPPacket(payload=audio_data, seq_num=self._rtp_seq, timestamp=self._rtp_ts, ssrc=user_id)
        if marker:
            pkt.marker = 1
        return pkt.pack()

    # ==================== TX 发射链路 (线程安全版本) ====================

    # 发射状态枚举
    class _TransmitState:
        """发射状态常量"""
        IDLE = 0
        STARTING = 1
        TRANSMITTING = 2
        STOPPING = 3
        BUFFERING = 4  # 预缓冲状态

    def start_transmit(self) -> bool:
        """
        开始发射 (PTT按下) - 线程安全版本

        启动录音 → Opus编码 → RTP发送 管道

        Returns:
            是否成功启动
        """
        logger.info("[TX] start_transmit 调用")

        if not self._socket or not self._is_listening:
            logger.warning("[TX] 错误: 未连接到语音服务器")
            return False

        # 快速路径检查 - 避免不必要的锁竞争
        with self._transmit_lock:
            current_state = getattr(self, '_tx_state', self._TransmitState.IDLE)

            if current_state == self._TransmitState.TRANSMITTING:
                logger.info("[TX] 已在发射中，忽略重复调用")
                return True

            if current_state in (self._TransmitState.STARTING, self._TransmitState.STOPPING):
                logger.warning(f"[TX] 状态转换中: {current_state}，忽略调用")
                return False

            # 状态转换: IDLE -> STARTING
            self._tx_state = self._TransmitState.STARTING

        try:
            # === 初始化阶段 (双重检查锁定，所有初始化都在锁内) ===
            with self._transmit_lock:
                # 再次检查状态，防止在等待锁时状态已改变
                if self._tx_state != self._TransmitState.STARTING:
                    logger.warning(f"[TX] 状态已改变，取消启动: {self._tx_state}")
                    return False

                # 初始化编码器 (只创建一次)
                if not hasattr(self, '_tx_encoder') or self._tx_encoder is None:
                    logger.debug("[TX] 初始化编码器")
                    from audio_codec import OpusEncoder, SAMPLE_RATE, FRAME_SIZE

                    self._tx_encoder = OpusEncoder(
                        sample_rate=SAMPLE_RATE,
                        frame_size=FRAME_SIZE,
                        bitrate=32000
                    )

                # 初始化录音器 (只创建一次，复用实例)
                if not hasattr(self, '_tx_recorder') or self._tx_recorder is None:
                    logger.debug("[TX] 初始化录音器")
                    from audio_codec import AudioRecorder, SAMPLE_RATE, FRAME_SIZE

                    self._tx_recorder = AudioRecorder(
                        sample_rate=SAMPLE_RATE,
                        frame_size=FRAME_SIZE,
                        channels=1
                    )

                # 确保录音流已打开 (保持常开，PTT按下时零延迟)
                if not self._tx_recorder.is_recording:
                    logger.debug("[TX] 启动录音流")
                    if not self._tx_recorder.start_recording():
                        raise RuntimeError("启动录音失败")

                # 初始化停止事件和标志
                if not hasattr(self, '_tx_stop_event') or self._tx_stop_event is None:
                    self._tx_stop_event = threading.Event()
                else:
                    self._tx_stop_event.clear()

                self._tx_first_packet = True  # Marker 位标志
                self._tx_frame_count = 0      # 帧计数
                self._tx_start_time = time.time()  # 开始时间

                # 状态转换: STARTING -> TRANSMITTING (原子操作)
                self._tx_state = self._TransmitState.TRANSMITTING

            # === 启动发射线程 (在锁外，避免死锁) ===
            self._tx_thread = threading.Thread(
                target=self._transmit_loop,
                name="TX-Transmit",
                daemon=True
            )
            self._tx_thread.start()

            logger.info("[TX] 🟢 开始发射")
            return True

        except ImportError as e:
            logger.error(f"[TX] 缺少依赖: {e}")
            # 回滚状态
            with self._transmit_lock:
                self._tx_state = self._TransmitState.IDLE
            return False
        except Exception as e:
            logger.error(f"[TX] 启动发射失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            # 回滚状态
            with self._transmit_lock:
                self._tx_state = self._TransmitState.IDLE
            return False

    def stop_transmit(self):
        """
        停止发射 (PTT松开) - 线程安全版本
        """
        logger.info("[TX] stop_transmit 调用")

        # 快速路径检查
        with self._transmit_lock:
            current_state = getattr(self, '_tx_state', self._TransmitState.IDLE)

            if current_state == self._TransmitState.IDLE:
                logger.info("[TX] 未在发射中，忽略停止调用")
                return

            if current_state == self._TransmitState.STOPPING:
                logger.info("[TX] 已在停止中，忽略重复调用")
                return

            # 状态转换: TRANSMITTING -> STOPPING
            self._tx_state = self._TransmitState.STOPPING

        # 发送停止信号 (在锁外，避免死锁)
        if hasattr(self, '_tx_stop_event') and self._tx_stop_event:
            self._tx_stop_event.set()

        # 等待发射线程结束
        if hasattr(self, '_tx_thread') and self._tx_thread and self._tx_thread.is_alive():
            logger.info("[TX] 等待发射线程结束...")
            self._tx_thread.join(timeout=2.0)

            if self._tx_thread.is_alive():
                logger.warning("[TX] 发射线程未在超时时间内结束")
            else:
                logger.debug("[TX] 发射线程已结束")

            self._tx_thread = None

        # 发送 TX_AUDIO_STOP 包 (空payload)
        try:
            self.send_audio(b'', marker=False)
            logger.info("[TX] 已发送 TX_AUDIO_STOP")
        except Exception as e:
            logger.warning(f"[TX] 发送停止包失败: {e}")

        # 回到空闲状态 (必须在发送停止包后)
        with self._transmit_lock:
            self._tx_state = self._TransmitState.IDLE

        logger.info("[TX] 🔴 停止发射")

        # 不停止录音器，保持录音状态以便下次快速启动
        # if hasattr(self, '_tx_recorder') and self._tx_recorder:
        #     self._tx_recorder.stop_recording()

        # 发送 TX_AUDIO_STOP 包 (空payload)
        try:
            self.send_audio(b'', marker=False)
            logger.info("[TX] 已发送 TX_AUDIO_STOP")
        except Exception as e:
            logger.warning(f"[TX] 发送停止包失败: {e}")

        logger.info("[TX] 🔴 停止发射")

    # ==================== Web PTT 发射 (无麦克风) ====================

    def start_transmit_web(self) -> bool:
        """
        开始 Web 端发射 — 不启动本地麦克风

        编码器懒加载一次，跨 PTT 会话复用（避免反复创建/销毁 C 资源）。
        TX 录音器在每次 PTT 会话开始时初始化。

        使用后台编码线程避免阻塞 Socket.IO 事件循环。

        Returns:
            是否成功启动
        """
        logger.info("[TX_WEB] start_transmit_web 调用")

        if not self._socket or not self._is_listening:
            logger.warning("[TX_WEB] 错误: 未连接到语音服务器")
            return False

        with self._transmit_lock:
            current_state = getattr(self, '_tx_state', self._TransmitState.IDLE)

            if current_state == self._TransmitState.TRANSMITTING:
                logger.info("[TX_WEB] 已在发射中")
                return True

            if current_state in (self._TransmitState.STARTING, self._TransmitState.STOPPING):
                logger.warning(f"[TX_WEB] 状态转换中: {current_state}")
                return False

            self._tx_state = self._TransmitState.STARTING

        try:
            # 初始化 PCM 队列（缓冲 50 帧 = 1 秒，容忍 SocketIO 传输抖动）
            if not hasattr(self, '_tx_web_pcm_queue'):
                self._tx_web_pcm_queue = queue.Queue(maxsize=50)
            else:
                # 清空队列（上次可能残留数据）
                while not self._tx_web_pcm_queue.empty():
                    try:
                        self._tx_web_pcm_queue.get_nowait()
                    except queue.Empty:
                        break

            # 重置累积缓冲区
            self._tx_web_pcm_accum = b''

            # 启动后台编码线程
            self._start_web_tx_encoder_thread()

            with self._transmit_lock:
                if self._tx_state != self._TransmitState.STARTING:
                    return False

                # 懒加载编码器 — 只创建一次，永不销毁，跨会话复用
                if not hasattr(self, '_tx_web_encoder') or self._tx_web_encoder is None:
                    from audio_codec import OpusEncoder, SAMPLE_RATE, FRAME_SIZE
                    self._tx_web_encoder = OpusEncoder(
                        sample_rate=SAMPLE_RATE,
                        frame_size=FRAME_SIZE,
                        bitrate=64000  # 64kbps
                    )
                    logger.info(f"[TX_WEB] 编码器已创建 ({SAMPLE_RATE}Hz, {FRAME_SIZE}帧, 64kbps)")

                self._tx_first_packet = True
                self._tx_frame_count = 0
                self._tx_start_time = time.time()
                self._tx_web_mode = True
                self._tx_web_recording_started = False

                # 获取 TX 录音器 (由 mixer 管理)
                self._tx_web_recorder = None
                if hasattr(self, '_mixer') and self._mixer and self._mixer._tx_recorder:
                    self._tx_web_recorder = self._mixer._tx_recorder

                # 获取用户信息
                profile = getattr(self._client, 'profile', None)
                self._tx_web_uid = profile.user_id if profile else 0
                self._tx_web_name = profile.nickname if profile else "Web"

                self._tx_state = self._TransmitState.BUFFERING  # 预缓冲状态开始

            logger.info("[TX_WEB] 🟢 开始发射 (Web) [后台编码模式]")
            return True

        except Exception as e:
            logger.error(f"[TX_WEB] 启动失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            with self._transmit_lock:
                self._tx_state = self._TransmitState.IDLE
            return False

    def feed_web_pcm(self, pcm_bytes: bytes):
        """
        接收 Web 端发来的 PCM 数据，通过累积缓冲区按帧切割后放入队列。

        累积缓冲区确保：
        - 不完整的 PCM 帧不会被丢弃（等待后续数据拼接）
        - 多帧粘包时正确切割为独立帧入队

        Raises:
            queue.Full: 当 PCM 队列已满时抛出，调用者应等待后重试
        """
        # 快速路径检查 (无锁) - 允许 BUFFERING 和 TRANSMITTING 状态接收数据
        current_state = getattr(self, '_tx_state', self._TransmitState.IDLE)
        if current_state not in (self._TransmitState.TRANSMITTING, self._TransmitState.BUFFERING):
            return

        if not pcm_bytes or len(pcm_bytes) < 2:
            return

        FRAME_BYTES = 1920  # 960 samples * 2 bytes/sample (Int16)

        # 追加到累积缓冲区
        accum = getattr(self, '_tx_web_pcm_accum', b'') + pcm_bytes

        # 按帧大小切割并入队
        while len(accum) >= FRAME_BYTES:
            frame_data = accum[:FRAME_BYTES]
            accum = accum[FRAME_BYTES:]
            # ✅ 关键修复：队列满时重新抛出异常，让调用者处理背压
            if hasattr(self, '_tx_web_pcm_queue'):
                self._tx_web_pcm_queue.put_nowait(frame_data)  # 队列满时会抛出 queue.Full

        self._tx_web_pcm_accum = accum

    def process_webrtc_audio(self, audio_data: bytes):
        """
        处理 WebRTC DataChannel 接收到的音频数据

        WebRTC DataChannel 直接传输 PCM 数据（无需解析帧边界），
        直接放入队列由编码线程处理。

        Args:
            audio_data: 原始 PCM 字节数据
        """
        # 快速路径检查 (无锁) - 允许 BUFFERING 和 TRANSMITTING 状态接收数据
        current_state = getattr(self, '_tx_state', self._TransmitState.IDLE)
        if current_state not in (self._TransmitState.TRANSMITTING, self._TransmitState.BUFFERING):
            return

        if not audio_data or len(audio_data) < 2:
            return

        # 直接放入队列（假设数据已经是完整的帧）
        try:
            if hasattr(self, '_tx_web_pcm_queue'):
                # 如果数据量较大，切分成多个帧
                FRAME_BYTES = 1920  # 960 samples * 2 bytes
                offset = 0
                while offset + FRAME_BYTES <= len(audio_data):
                    frame_data = audio_data[offset:offset + FRAME_BYTES]
                    try:
                        self._tx_web_pcm_queue.put_nowait(frame_data)
                    except queue.Full:
                        logger.warning("[TX_WEB] WebRTC PCM 队列已满，丢弃帧")
                        break
                    offset += FRAME_BYTES

                # 处理剩余的不完整帧，追加到累积缓冲区
                if offset < len(audio_data):
                    remaining = audio_data[offset:]
                    accum = getattr(self, '_tx_web_pcm_accum', b'') + remaining
                    self._tx_web_pcm_accum = accum
        except Exception as e:
            logger.error(f"[TX_WEB] 处理 WebRTC 音频错误: {e}")

    def _start_web_tx_encoder_thread(self):
        """启动 Web 发射的后台编码线程"""
        if not hasattr(self, '_tx_web_encoder_thread') or not self._tx_web_encoder_thread or not self._tx_web_encoder_thread.is_alive():
            self._tx_web_encoder_thread = threading.Thread(
                target=self._web_tx_encoder_loop,
                daemon=True,
                name="WebTxEncoder"
            )
            self._tx_web_encoder_thread.start()
            logger.info("[TX_WEB] 编码线程已启动")

    def _web_tx_encoder_loop(self):
        """
        Web 发射编码线程：从队列取 PCM → Opus编码 → RTP发送

        前端每个 SocketIO 事件携带 2 帧 (3840字节)，feed_web_pcm 自动
        拆为 2 个 960 样本帧入队。队列实际入帧率 ~50fps。

        使用 monotonic 时钟节拍确保 RTP 包间距稳定 20ms。
        """
        import numpy as np
        from audio_codec import FRAME_SIZE

        logger.info("[TX_WEB] 编码线程开始运行")
        last_log_time = time.time()
        frames_in_last_second = 0
        FRAME_INTERVAL = 0.020  # 20ms
        PREBUFFER_FRAMES = 15  # 预缓冲 15 帧 (300ms)，匹配前端 100ms 发送间隔
        FRAME_BYTES = 1920      # 960 samples * 2 bytes
        SILENCE_FRAME = bytes(FRAME_BYTES)  # 静音帧
        send_clock = None

        while True:
            current_state = getattr(self, '_tx_state', self._TransmitState.IDLE)

            # ✅ 检查 STOPPING 状态，退出编码线程
            if current_state == self._TransmitState.STOPPING:
                logger.info("[TX_WEB] 检测到停止信号，编码线程退出")
                break

            # BUFFERING 状态：等待预缓冲完成
            if current_state == self._TransmitState.BUFFERING:
                qsize = self._tx_web_pcm_queue.qsize() if hasattr(self, '_tx_web_pcm_queue') else 0
                if qsize >= PREBUFFER_FRAMES:
                    # 缓冲完成，切换到 TRANSMITTING
                    with self._transmit_lock:
                        self._tx_state = self._TransmitState.TRANSMITTING
                    current_state = self._TransmitState.TRANSMITTING  # 更新局部变量
                    send_clock = time.monotonic()  # 重置时钟
                    logger.info(f"[TX_WEB] 预缓冲完成，开始发送 ({qsize} 帧)")
                else:
                    time.sleep(0.01)  # 等待更多帧
                    continue

            # 检查是否仍在发射
            if current_state != self._TransmitState.TRANSMITTING:
                send_clock = None
                time.sleep(0.01)
                continue

            try:
                # 从队列获取 PCM 帧（阻塞等待）
                try:
                    pcm_bytes = self._tx_web_pcm_queue.get(timeout=0.001)  # 缩短等待时间
                except queue.Empty:
                    # 队列为空，发送静音帧保持节奏
                    pcm_bytes = SILENCE_FRAME
                    silent_frames_sent = getattr(self, '_silent_frame_count', 0) + 1
                    self._silent_frame_count = silent_frames_sent
                    if silent_frames_sent % 100 == 0:
                        logger.warning(f"[TX_WEB] 发送静音帧: {silent_frames_sent}")

                pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
                if len(pcm_array) < FRAME_SIZE:
                    continue

                frame = np.ascontiguousarray(pcm_array[:FRAME_SIZE])

                # 首帧到达时开始 TX 录音
                if not self._tx_web_recording_started and self._tx_web_recorder:
                    self._tx_web_recorder.on_speaker_start(self._tx_web_uid, self._tx_web_name)
                    self._tx_web_recording_started = True
                    logger.info(f"[TX_WEB] TX 录音已开始 (uid={self._tx_web_uid})")

                # 写入 TX 录音器
                if self._tx_web_recorder:
                    self._tx_web_recorder.write_pcm(self._tx_web_uid, frame.tobytes())

                # 20ms 时钟节拍 — 确保 RTP 包间距稳定
                now = time.monotonic()
                if send_clock is None:
                    send_clock = now
                else:
                    wait = send_clock - now
                    if wait > 0.001:
                        time.sleep(wait)
                    elif wait < -0.5:
                        # 落后太多，重置
                        send_clock = now

                # Opus 编码 + RTP 发射
                opus_data = self._tx_web_encoder.encode(frame)
                if opus_data:
                    is_first = self._tx_first_packet
                    if is_first:
                        self._tx_first_packet = False
                    self.send_audio(opus_data, marker=is_first)
                    self._tx_frame_count += 1
                    frames_in_last_second += 1

                # 推进时钟
                send_clock += FRAME_INTERVAL

                # 每 50 帧记录统计
                if self._tx_frame_count % 50 == 0:
                    now_t = time.time()
                    dt = now_t - last_log_time
                    fps = frames_in_last_second / max(0.001, dt)
                    qd = self._tx_web_pcm_queue.qsize()
                    logger.info(f"[TX_WEB] 进度: {self._tx_frame_count * 0.02:.1f}s, "
                              f"{self._tx_frame_count} 帧, 队列={qd}, 帧率={fps:.0f}fps")
                    frames_in_last_second = 0
                    last_log_time = now_t

            except Exception as e:
                logger.error(f"[TX_WEB] 编码线程异常: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                send_clock = None
                time.sleep(0.1)

    def stop_transmit_web(self):
        """停止 Web 端发射，结束 TX 录音。不销毁编码器（复用）。"""
        logger.info("[TX_WEB] stop_transmit_web 调用")

        with self._transmit_lock:
            current_state = getattr(self, '_tx_state', self._TransmitState.IDLE)
            # 允许 BUFFERING 和 TRANSMITTING 状态都能停止
            if current_state not in (self._TransmitState.TRANSMITTING, self._TransmitState.BUFFERING):
                return
            self._tx_state = self._TransmitState.STOPPING

        # 获取编码锁 — 等待正在进行的 feed_web_pcm 完成
        if hasattr(self, '_tx_web_encode_lock'):
            self._tx_web_encode_lock.acquire()
            self._tx_web_encode_lock.release()

        # 发送 TX_AUDIO_STOP 包
        try:
            self.send_audio(b'', marker=False)
            logger.info("[TX_WEB] 已发送 TX_AUDIO_STOP")
        except Exception as e:
            logger.warning(f"[TX_WEB] 发送停止包失败: {e}")

        # 结束 TX 录音
        duration = self._tx_frame_count * 0.02
        if self._tx_web_recording_started and self._tx_web_recorder:
            self._tx_web_recorder.on_speaker_end(
                self._tx_web_uid, duration, self._tx_frame_count, 0, 0
            )
            logger.info(f"[TX_WEB] TX 录音已保存 ({duration:.2f}s)")

        # 不销毁编码器 — 跨 PTT 会话复用
        with self._transmit_lock:
            self._tx_state = self._TransmitState.IDLE
            self._tx_web_mode = False

        logger.info(f"[TX_WEB] 🔴 停止发射 (Web): {self._tx_frame_count} 帧, {duration:.2f}s")

    def _transmit_loop(self):
        """
        发射线程: 录音 → Opus编码 → RTP发送
        """
        import numpy as np
        import time

        frame_count = 0
        tx_recorder = None
        tx_recording_started = False
        user_id = getattr(self._client, 'profile', None)
        uid = user_id.user_id if user_id else 0
        name = user_id.nickname if user_id else "本机"

        # 获取 TX 录音器
        if hasattr(self, '_mixer') and self._mixer and self._mixer._tx_recorder:
            tx_recorder = self._mixer._tx_recorder

        logger.debug(f"[TX_LOOP] 发射循环线程开始")

        iteration = 0

        # 使用状态检查而不是_is_transmitting标志
        while not self._tx_stop_event.is_set():
            # 检查状态 - 只在TRANSMITTING状态时继续
            with self._transmit_lock:
                current_state = getattr(self, '_tx_state', self._TransmitState.IDLE)
                if current_state != self._TransmitState.TRANSMITTING:
                    logger.debug(f"[TX_LOOP] 状态已改变: {current_state}，退出循环")
                    break

            iteration += 1
            try:
                # 1. 读取一帧 PCM (阻塞, 20ms)
                pcm_frame = self._tx_recorder.read_frame(timeout_ms=100)

                if pcm_frame is None:
                    logger.debug(f"[TX_LOOP] read_frame 返回 None (iteration={iteration})")
                    break

                # 第一帧到达时才开始 TX 录音
                if not tx_recording_started and tx_recorder:
                    logger.info(f"[TX_LOOP] 第一帧到达，开始 TX 录音 (uid={uid})")
                    tx_recorder.on_speaker_start(uid, name)
                    tx_recording_started = True

                # 2. 转换为 bytes 并写入 TX 录音
                pcm_bytes = pcm_frame.tobytes()
                if tx_recorder:
                    tx_recorder.write_pcm(uid, pcm_bytes)

                # 3. Opus 编码
                opus_data = self._tx_encoder.encode(pcm_frame)
                if not opus_data:
                    logger.warning("Opus 编码失败")
                    continue

                # 4. RTP 发送 (首包设置 Marker 位)
                is_first = self._tx_first_packet
                if is_first:
                    self._tx_first_packet = False

                self.send_audio(opus_data, marker=is_first)
                frame_count += 1
                self._tx_frame_count = frame_count

                # 每 50 帧打印一次进度 (1秒)
                if frame_count % 50 == 0:
                    elapsed = frame_count * 0.02  # 使用帧数计算时长
                    logger.info(f"[TX] 发射进度: {elapsed:.1f}s, {frame_count} 帧")

            except Exception as e:
                logger.error(f"发射循环异常 (iteration={iteration}): {e}")
                import traceback
                logger.debug(traceback.format_exc())
                break

        # 计算实际发射时长
        duration = frame_count * 0.02  # 每帧 20ms
        logger.info(f"[TX_LOOP] 发射循环结束: {frame_count} 帧, {duration:.2f}s, tx_recording_started={tx_recording_started}")

        # 通知 TX 录音器结束
        if tx_recorder and tx_recording_started:
            tx_recorder.on_speaker_end(uid, duration, frame_count, 0, 0)

    @property
    def is_transmitting(self) -> bool:
        """是否正在发射 - 线程安全"""
        with self._transmit_lock:
            return getattr(self, '_tx_state', self._TransmitState.IDLE) == self._TransmitState.TRANSMITTING

    def start_ptt_keyboard(self) -> bool:
        """
        启动键盘 PTT 控制 (空格键)

        按住空格键说话，释放停止

        Returns:
            是否成功启动
        """
        if not self._socket or not self._is_listening:
            print("[PTT] 错误: 未连接到语音服务器")
            return False

        if hasattr(self, '_ptt_keyboard_active') and self._ptt_keyboard_active:
            print("[PTT] 键盘控制已启动")
            return True

        try:
            import keyboard

            self._ptt_keyboard_active = True
            space_pressed = False

            print("\n" + "=" * 60)
            print("PTT 键盘控制启动")
            print("=" * 60)
            print("说明:")
            print("  - 按住空格键说话")
            print("  - 释放空格键停止")
            print("  - 按 Ctrl+C 退出")
            print("=" * 60)

            import time

            # 防抖动: 记录最后一次按键时间
            last_key_time = 0
            DEBOUNCE_MS = 50  # 50ms 防抖动

            def on_press(event):
                nonlocal space_pressed, last_key_time
                # 检查是否是空格键
                if event.name == 'space':
                    current_time = time.time() * 1000  # ms
                    # 防抖动检查
                    if current_time - last_key_time < DEBOUNCE_MS:
                        return

                    if not space_pressed:
                        space_pressed = True
                        last_key_time = current_time
                        logger.debug("PTT 按下事件检测")
                        if self.start_transmit():
                            print(">>> 开始录音")
                        else:
                            print("!!! 启动失败")

            def on_release(event):
                nonlocal space_pressed, last_key_time
                # 检查是否是空格键
                if event.name == 'space':
                    current_time = time.time() * 1000  # ms
                    # 防抖动检查
                    if current_time - last_key_time < DEBOUNCE_MS:
                        return

                    if space_pressed:
                        space_pressed = False
                        last_key_time = current_time
                        logger.debug("PTT 释放事件检测")
                        self.stop_transmit()
                        print("|| 停止录音")

            keyboard.hook(on_press)
            keyboard.hook(on_release)

            keyboard.wait()

        except ImportError:
            print("[PTT] 错误: keyboard 模块未安装")
            print("       请运行: pip install keyboard")
            return False
        except KeyboardInterrupt:
            print("\n\n[PTT] 用户中断")
        except Exception as e:
            print(f"[PTT] 键盘监听失败: {e}")
            return False
        finally:
            self.stop_ptt_keyboard()

        return True

    def stop_ptt_keyboard(self):
        """停止键盘 PTT 控制"""
        if not hasattr(self, '_ptt_keyboard_active') or not self._ptt_keyboard_active:
            return

        self._ptt_keyboard_active = False

        try:
            import keyboard
            keyboard.unhook_all()
        except ImportError:
            # keyboard 模块未安装
            pass
        except Exception as e:
            # 忽略键盘清理错误
            pass

        if self.is_transmitting:
            self.stop_transmit()

        print("[PTT] 键盘控制已停止")

    def _build_register_packet(self) -> bytes:
        """
        构建 UDP 注册包 (使用 Heartbeat)
        """
        return self._build_heartbeat_packet()
        
    def _build_heartbeat_packet(self) -> bytes:
        """
        构建 UDP 心跳包 (MessagePack)
        """
        user_id = self._client.profile.user_id if self._client.profile else 0
        # Java logic: I = ((5000 / 1000) * 2) + 8 = 18. V is 0 (not set).
        # We try to mimic this exact behavior.
        hb = Heartbeat(uid=user_id, interval=18, version=0) 
        packed = hb.pack()
        # DEBUG LOG
        logger.debug(f"Heartbeat Hex: {packed.hex()}")
        logger.debug(f"Target: {self._server_ip}:{self._server_port} | UserID: {user_id}")
        return packed


# ==================== 测试入口 ====================

def main():
    """测试入口"""
    import sys
    
    print("=" * 60)
    print("BSHT 完整客户端 - 功能测试")
    print("=" * 60)
    
    # 获取账号密码
    if len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
    else:
        username = "bswxd"
        password = "BsWxd2026"
        print(f"使用默认账号: {username}")
    
    # 创建客户端 (启用 Token 自动刷新)
    client = BSHTClient(auto_refresh_token=True)
    
    # 设置 Token 刷新回调
    def on_token_refreshed(token_info: TokenInfo):
        print(f"\n[Token 自动刷新] access_token 已更新")
        client.save_credentials()
    
    client.set_token_refresh_callback(on_token_refreshed)
    
    try:
        # 1. 登录
        print("\n[1] 登录测试...")
        result = client.login(username, password)
        if not result.success:
            print(f"  ✗ 登录失败: {result.error}")
            return
        print(f"  ✓ 登录成功")
        print(f"    access_token: {client.access_token[:20]}...")
        
        # 2. Token 状态
        print("\n[2] Token 状态...")
        token_status = client.get_token_status()
        print(f"  ✓ 有效期剩余: {token_status['expires_in']} 秒")
        print(f"    刷新令牌剩余: {token_status['refresh_expires_in']} 秒")
        print(f"    需要刷新: {token_status['needs_refresh']}")
        
        # 3. 加载用户资料
        print("\n[3] 加载用户资料...")
        result = client.load_profile()
        if result.success:
            profile = result.data
            print(f"  ✓ 用户ID: {profile.user_id}")
            print(f"    用户名: {profile.username}")
            print(f"    昵称: {profile.nickname}")
            print(f"    邮箱: {profile.email}")
        
        # 4. 获取用户频道
        print("\n[4] 获取用户加入的频道...")
        result = client.get_user_channels()
        test_channel_id = None
        if result.success:
            channels = result.data
            print(f"  ✓ 已加入 {len(channels)} 个频道")
            for ch in channels:
                admin_mark = "[管理员]" if ch.is_admin else ""
                print(f"    - [{ch.channel_id}] {ch.name} {admin_mark}")
            
            if channels:
                test_channel_id = channels[0].channel_id
        
        # 5. 获取语音连接参数
        if test_channel_id:
            print(f"\n[5] 获取语音连接参数 (频道: {test_channel_id})...")
            result = client.get_channel_connection_params(test_channel_id)
            if result.success:
                params: ChannelConnectionParams = result.data
                print(f"  ✓ 语音服务器: {params.ip}:{params.port}")
                print(f"    比特率: {params.bit_rates}")
                print(f"    管理员: {params.is_admin}")
                print(f"    通话优先级: {params.call_priority}")
                if params.rf_config:
                    print(f"    无线电配置: TX={params.rf_config.get('txFreq', 0)}Hz, RX={params.rf_config.get('rxFreq', 0)}Hz")
            else:
                print(f"  ✗ 获取语音参数失败: {result.error}")
        
        # 6. 测试音频流监听器
        if test_channel_id:
            print(f"\n[6] 测试音频流监听器...")
            listener = AudioStreamListener(client)
            
            # 设置回调
            def on_audio(frame: AudioFrame):
                print(f"    收到音频帧: 用户={frame.user_id}, 数据长度={len(frame.data)}")
            
            def on_error(msg: str):
                print(f"    错误: {msg}")
            
            listener.set_callbacks(on_audio_frame=on_audio, on_error=on_error)
            
            # 连接
            result = listener.connect(test_channel_id)
            if result.success:
                conn_info = result.data
                print(f"  ✓ 已连接到语音服务器: {conn_info['ip']}:{conn_info['port']}")
                
                # 尝试启动监听 (可能会失败，取决于实际协议)
                print(f"    启动监听...")
                if listener.start_listening():
                    print(f"  ✓ 音频流监听已启动")
                    # 监听 3 秒
                    print(f"    监听 3 秒...")
                    time.sleep(3)
                    listener.stop_listening()
                    print(f"  ✓ 停止监听")
                else:
                    print(f"  ⚠ 无法启动监听 (可能需要分析实际协议)")
            else:
                print(f"  ✗ 连接失败: {result.error}")
        
        # 7. 保存凭证
        print("\n[7] 保存凭证...")
        if client.save_credentials():
            print("  ✓ 凭证已保存到 credentials.json")
        
        print("\n" + "=" * 60)
        print("测试完成!")
        print("=" * 60)
        
        print("\n提示: 音频流监听需要进一步分析实际协议才能正常工作")
        print("      建议使用 Wireshark 抓包分析语音数据格式")
        
    except KeyboardInterrupt:
        print("\n\n正在退出...")
    finally:
        client.close()


if __name__ == "__main__":
    main()