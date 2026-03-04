[根目录](../CLAUDE.md) > [Python 根目录](../) > **bsht_client.py**

---

# BSHT Client 模块

## 模块职责

完整的 gRPC 客户端实现，负责与 BSHT 服务的通信。提供用户认证、频道管理、音频流监听等功能。

## 入口与启动

```python
from bsht_client import BSHTClient, TokenInfo, StatusCode, ChannelConnectionParams

# 创建客户端 (自动刷新 Token)
client = BSHTClient(auto_refresh_token=True)

# 登录
login_result = client.login(username, password)

# 获取频道列表
channels_resp = client.get_user_channels(offset=0, limit=20)

# 加入频道
join_result = client.join_channel(channel_id, passcode=0)
```

## 对外接口

### 认证 API
- `login(username, password)` - 用户登录
- `refresh_access_token()` - 刷新 Access Token
- `load_profile()` - 加载用户资料

### 频道管理 API
- `get_channels(offset, limit)` - 获取频道列表
- `get_user_channels(offset, limit)` - 获取用户加入的频道
- `join_channel(channel_id, passcode)` - 加入频道
- `leave_channel(channel_id)` - 离开频道
- `get_channel_status(channel_id)` - 获取频道状态
- `get_channel_members(channel_id)` - 获取频道成员
- `get_channel_connection_params(channel_id)` - 获取连接参数

### 音频流 API
- `start_audio_listener(channel_id, params)` - 启动音频监听
- `stop_audio_listener()` - 停止音频监听
- `send_audio(frame)` - 发送音频帧

## 关键依赖

- `httpx[http2]` - HTTP/2 客户端
- `msgpack` - 消息序列化
- `src/bsht/protocol/` - 协议实现

## 数据模型

```python
class StatusCode(IntEnum):
    OK = 0
    ERR_NAME_OR_PASSWORD = 1
    ERR_USER_HAVE_NO_PASSWORD = 2
    ERR_NOT_LOGIN = 3
    ERR_UNCONFIRMED = 4

@dataclass
class TokenInfo:
    access_token: str
    access_token_expires: int
    refresh_token: str
    refresh_token_expires: int

@dataclass
class ChannelInfo:
    channel_id: int
    name: str
    has_passcode: bool
    user_count: int

@dataclass
class ChannelConnectionParams:
    server_ip: str
    server_port: int
    rtp_port: int
    ssrc: int
    token: str
```

## 常见问题

- **Token 过期**: 客户端自动刷新，需确保 `auto_refresh_token=True`
- **频道密码**: 部分频道需要密码，通过 `join_channel(channel_id, passcode)` 传入
- **音频监听**: 需要先加入频道，再获取连接参数启动监听

## 相关文件

- `bot_server.py` - 使用本模块的服务器实现
- `src/bsht/protocol/` - 底层协议实现
- `audio_codec.py` - 音频编解码（配合使用）

---

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-02-27 | 创建模块文档 |
