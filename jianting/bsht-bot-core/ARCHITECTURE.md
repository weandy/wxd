# BSHT Bot Core 架构分析文档

> 基于代码深度分析，不参考外部文档
> 最后更新: 2026-02-26

---

## 一、项目概述

BSHT Bot Core 是一个基于 Python 的纯 Bot 核心模块，实现了与 BSHT (Ham Radio/即时通讯) 平台的双向通信。系统采用**分层架构**和**事件驱动**模式。

### 核心特性

| 特性 | 说明 |
|------|------|
| gRPC 通信 | 连接 BSHT 服务器，用户认证、频道管理 |
| 实时语音 | Opus 编解码，48kHz Fullband |
| 多用户混音 | 支持多人同时通话 |
| 频道录音 | 按用户/日期分类存储 |
| 语音识别 | 伪实时识别录音文件 |
| 微信推送 | 识别结果推送到微信 |
| 控制台 PTT | 键盘按键说话 |

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     应用层 (bot_server.py)                   │
│                 主循环控制、认证、频道管理                    │
├─────────────────────────────────────────────────────────────┤
│                     业务逻辑层                               │
│    AudioMixer    │    ChannelRecorder    │    PTT 控制     │
├─────────────────────────────────────────────────────────────┤
│                     通信层 (bsht_client.py)                │
│    BSHTClient    │    AudioStreamListener (UDP)           │
├─────────────────────────────────────────────────────────────┤
│                     协议层 (ht_protocol.py)                │
│      RTP 包解析    │    心跳包    │    二进制协议          │
├─────────────────────────────────────────────────────────────┤
│                     音频处理层                              │
│  JitterBuffer   │   Opus 编解码   │   AudioProcessor      │
├─────────────────────────────────────────────────────────────┤
│                     识别/智能层                             │
│  RecordingRecognizer  │  SmartAudioProcessor  │ WxPusher │
├─────────────────────────────────────────────────────────────┤
│                     数据层                                  │
│            SQLite Database  │  录音文件存储                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块详解

### 3.1 bot_server.py - 主服务器

**文件**: `bot_server.py` (~1200 行)

**核心类**: `BotServer`

**职责**:
- 用户认证与 Token 管理
- 频道加入/退出管理
- 语音服务器连接
- 主业务循环控制

**启动流程**:

```
bot_server.start()
    ↓
_login() → BSHTClient.login()
    ↓
_main_loop()
    ├─ get_user_channels() → 检查是否已加入频道
    ├─ join_channel() → 加入目标频道
    ├─ listener.connect() → 连接语音服务器
    ├─ listener.start_listening() → 启动UDP监听
    ├─ _keep_alive_loop() → 保活循环
    └─ 退出 → 关闭 recorder/listener
```

**核心方法**:

| 方法 | 职责 |
|------|------|
| `__init__()` | 初始化客户端、异步组件、性能监控 |
| `start()` | 启动机器人主循环 |
| `stop()` | 停止机器人并清理所有资源 |
| `_login()` | 处理登录逻辑（支持凭证缓存） |
| `_main_loop()` | 主业务循环 |
| `_keep_alive_loop()` | 保活循环，30秒检查一次 |
| `_process_pending_commands()` | 轮询 Web 命令（纯 Bot 模式下跳过） |
| `_setup_recorder()` | 设置录音器 |

---

### 3.2 bsht_client.py - gRPC 客户端

**文件**: `bsht_client.py` (~2200 行)

**核心类**:

| 类名 | 职责 |
|------|------|
| `ProtobufCodec` | Protocol Buffers 编解码 |
| `GrpcClient` | gRPC 底层通信 |
| `TokenManager` | Token 自动刷新管理 |
| `BSHTClient` | 完整客户端 API 封装 |
| `AudioStreamListener` | UDP 音频流监听 |

**BSHTClient API**:

```python
# 认证
login(username, password) → ApiResponse
login_with_token(access_token, refresh_token) → ApiResponse
load_profile() → ApiResponse

# 频道管理
get_user_channels() → ApiResponse
join_channel(channel_id, passcode) → ApiResponse
get_channel_status(channel_id) → ApiResponse
get_channel_connection_params(channel_id) → ApiResponse
get_channel_members(channel_id) → ApiResponse

# 音频流
AudioStreamListener.connect(channel_id) → bool
AudioStreamListener.start_listening() → bool
AudioStreamListener.stop_transmit() → bool
```

**TokenManager 机制**:
- 自动刷新 Token (每 55 分钟)
- 凭证持久化 (保存到 credentials.json)
- Token 过期自动重新登录

**AudioStreamListener**:
- UDP 监听语音服务器
- RTP 包解析
- 回调 `on_audio_frame(AudioFrame)`
- 回调 `on_speaking_state_changed(user_id, is_speaking)`

---

### 3.3 ht_protocol.py - 协议处理

**文件**: `ht_protocol.py` (~184 行)

**核心类**:

| 类名 | 功能 |
|------|------|
| `BinaryPacket` | 二进制数据包解析/构建 |
| `Heartbeat` | 心跳包 (MessagePack 格式) |
| `RTPPacket` | RTP 音频包解析/构建 |
| `HTPacket` | 统一包解析入口 |

**协议格式**:

1. **Heartbeat (心跳)**
   ```
   格式: \x00 + msgpack(U=uid, I=interval, V=version)
   用途: 保持 UDP 连接活跃
   周期: 5 秒
   ```

2. **RTP (实时传输协议)**
   ```
   头部: 12 字节
   - V(2bit): 版本
   - P(1bit): 填充
   - X(1bit): 扩展
   - CC(4bit): CSRC 计数
   - M(1bit): 标记位
   - PT(7bit): 负载类型 (98=opus)
   - Sequence Number (16bit)
   - Timestamp (32bit)
   - SSRC (32bit): 同步源标识

   负载: Opus 编码音频数据
   用途: 实时语音传输
   ```

3. **BinaryPacket (二进制)**
   ```
   格式: Tag(1B) + Length(2B) + Value
   用途: 登录认证、控制指令
   ```

**关键常量**:

```python
SAMPLE_RATE = 48000      # 48kHz (Fullband)
FRAME_SIZE = 960        # 20ms @ 48kHz
CHANNELS = 1            # 单声道
PTT_HOLD_TIMEOUT = 0.30  # 300ms 无按键 = 松开
```

---

### 3.4 jitter_buffer.py - 抖动缓冲

**文件**: `jitter_buffer.py` (~215 行)

**核心类**: `JitterBuffer`

**功能**:
- 按序列号重排 RTP 包
- 检测丢包并标记 (用于 PLC)
- 检测说话者切换 (SSRC 变化)
- 可配置缓冲深度

**工作原理**:

```
接收线程 (push):
  RTP包(seq=100) → 存入 buffer[100]
  RTP包(seq=101) → 存入 buffer[101]
  RTP包(seq=103) → 存入 buffer[103]  # 102 丢包

播放线程 (pop):
  buffer[next_seq=100] → 解码播放
  buffer[next_seq=101] → 解码播放
  buffer[next_seq=102] → 返回 None → 触发 PLC
```

**关键参数**:

```python
target_depth = 3    # 目标缓冲深度 (帧数)
max_depth = 50      # 最大缓冲深度
```

**统计指标**:
- `total_pushed`: 接收帧数
- `total_popped`: 播放帧数
- `total_lost`: 丢包数
- `total_late`: 迟到丢弃数
- `loss_rate`: 丢包率

---

### 3.5 audio_mixer.py - 音频混音

**文件**: `audio_mixer.py` (~334 行)

**核心类**: `AudioMixer`, `UserStream`

**功能**:
- 多用户音频流管理
- 每用户独立 JitterBuffer + OpusDecoder
- 混音输出
- 会话统计与回调

**架构**:

```
用户A → JitterBuffer_A → Decoder_A → PCM_A ─┐
用户B → JitterBuffer_B → Decoder_B → PCM_B ─┼→ mix() → 播放
用户C → JitterBuffer_C → Decoder_C → PCM_C ─┘
```

**关键方法**:

| 方法 | 职责 |
|------|------|
| `add_user(ssrc)` | 添加用户流 |
| `remove_user(ssrc)` | 移除用户流 |
| `push(ssrc, sequence, opus_data)` | 接收 RTP 帧 |
| `pop_mixed()` | 取出混音后的 PCM |
| `_mix_pcm()` | 多路 PCM 混音算法 |

**特殊机制**:

1. **解码器预创建池**: 避免首帧到达时才创建解码器导致的 300ms 延迟

2. **序列号大跳跃检测**: 超过 100 帧的"丢包"自动重置 session，避免 PLC 噪声

3. **用户活跃超时**: 0.3 秒无数据 → 用户不再活跃

---

### 3.6 audio_codec.py - 音频编解码

**文件**: `audio_codec.py` (~700 行)

**核心类**:

| 类名 | 功能 |
|------|------|
| `OpusDecoder` | Opus 解码器 (DLL 调用) |
| `OpusEncoder` | Opus 编码器 |
| `AudioRecorder` | 音频采集器 (PyAudio) |
| `AudioPlayer` | 音频播放器 (PyAudio) |

**Opus 配置**:

```python
sample_rate: 48000 Hz      # Fullband
frame_size: 960           # 20ms
channels: 1               # 单声道
bitrate: 32000 bps        # 可调
application: VOIP         # 模式
```

**DLL 缓存机制**:
- 类级别 `_shared_lib` 缓存
- 首次加载后复用，避免重复磁盘 I/O

**PLC (Packet Loss Concealment)**:
- 解码器内置丢包补偿
- `decode(None)` 调用 PLC

---

### 3.7 channel_recorder.py - 频道录音

**文件**: `channel_recorder.py` (~313 行)

**核心类**: `ChannelRecorder`, `_ActiveRecording`

**功能**:
- 频道对话录制
- 按日期/用户分类存储
- WAV 格式保存
- 伪实时识别回调

**文件组织**:

```
recordings/
└── 2026-02-26/
    ├── 001_123456_153045.wav    # 格式: 序号_用户ID_时间.wav
    ├── 002_789012_160230.wav
    └── conversation_log.json     # 录制日志
```

**回调机制**:

```python
on_recording_complete(
    filepath,          # 录音文件路径
    duration,         # 录音时长(秒)
    start_time,       # 开始时间
    user_id,          # 用户 ID
    user_name,        # 用户昵称
    channel_id,       # 频道 ID
    recorder_type,    # RX/TX
    lost_frames,      # 丢包帧数
    loss_rate         # 丢包率
)
```

---

### 3.8 audio_processor.py - 音频预处理

**文件**: `audio_processor.py` (~153 行)

**核心类**: `AudioProcessor`

**功能**:
- 高通滤波 (80Hz) - 滤除风噪/低频噪声
- AGC 归一化 - 统一音量

**设计原则**:

> 录音阶段只做安全的、非破坏性的处理。激进降噪放在后处理阶段。

**处理流程**:

```
PCM输入 → 高通滤波(80Hz) → AGC归一化 → PCM输出
```

**AGC 参数**:

```python
target_peak_db: -3.0    # 目标峰值
gain_attack: 0.01       # 快速降低增益 (防削顶)
gain_release: 0.001     # 缓慢提升增益 (避免噪声放大)
max_gain: 10.0          # 最大增益限制
```

---

## 四、src/ 目录模块

### 4.1 src/main.py - 应用入口

**职责**:
- 配置加载 (.env)
- 数据库初始化
- 识别器启动
- 伪实时识别流程

### 4.2 src/database.py - 数据持久化

**核心类**: `Database`, `AudioRecord`, `Recording`

**数据库表**:

```sql
-- recordings 表
CREATE TABLE recordings (
    id INTEGER PRIMARY KEY,
    filepath TEXT,
    filename TEXT,
    channel_id INTEGER,
    user_id TEXT,
    user_name TEXT,
    recorder_type TEXT,    -- RX/TX
    duration REAL,
    start_time TEXT,
    file_size INTEGER,
    timestamp TEXT,
    recognized INTEGER,
    asr_text TEXT,
    content_normalized TEXT,
    signal_type TEXT,
    confidence REAL,
    rms_db REAL,
    snr_db REAL,
    recognize_duration REAL,
    invalid_reason TEXT
);

-- 微信推送服务表
CREATE TABLE notify_services (
    id INTEGER PRIMARY KEY,
    name TEXT,
    type TEXT,
    url TEXT,
    token TEXT,
    config TEXT,
    enabled INTEGER
);

CREATE TABLE notify_users (
    id INTEGER PRIMARY KEY,
    service_id INTEGER,
    name TEXT,
    user_identifier TEXT,
    keywords TEXT,
    enabled INTEGER
);
```

### 4.3 src/smart_processor.py - 智能音频处理

**核心类**:

| 类名 | 功能 |
|------|------|
| `AudioQualityAnalyzer` | 音频质量分析 (SNR 检测) |
| `AIClient` | AI API 调用 (SiliconFlow) |
| `SmartAudioProcessor` | 完整处理管线 |

**处理流程**:

```
WAV文件 → 音频质量分析
           ↓
         是否需要 DSP? → 是 → 降噪处理
           ↓
         ASR 语音识别
           ↓
         信号类型判断 (CQ/QSO/NOISE)
           ↓
         结果返回
```

**AI 配置**:

```python
base_url: "https://api.siliconflow.cn/v1"
model: "paraformer-realtime-v2"  # 实时语音识别
```

### 4.4 src/recognizer.py - 识别器

**核心类**: `RecordingRecognizer`

**功能**:
- 伪实时监听录音完成事件
- 并发识别 (3 个工作线程)
- 数据库结果存储

**并发设计**:

```python
max_workers = 3              # 线程池大小
_pending_queue = []          # 待识别队列
_executor = ThreadPoolExecutor()  # 线程池执行器
```

### 4.5 src/config.py - 配置管理

**配置类**: `AppConfig`, `BSHTConfig`, `APIConfig`, `DatabaseConfig`

**环境变量**:

```bash
# BSHT 配置
BSHT_USERNAME
BSHT_PASSWORD
BSHT_CHANNEL_ID
BSHT_CHANNEL_PASSCODE

# API 配置
SILICONFLOW_API_KEY
SILICONFLOW_BASE_URL

# 数据库配置
DATABASE_PATH
DATABASE_MAX_RECORDS

# 微信推送
WXPUSH_URL
WXPUSH_TOKEN
WXPUSH_TARGETS

# 日志
LOG_LEVEL
```

### 4.6 src/wx_pusher.py - 微信推送

**核心类**: `WxPusher`, `PushTarget`

**功能**:
- 基于 go-wxpush 服务
- 关键词触发推送
- 多用户推送

---

## 五、完整数据流

### 5.1 接收音频流程

```
BSHT 服务器 (gRPC)
    ↓ RTP 流
AudioStreamListener (UDP 监听)
    ↓
ht_protocol.RTPPacket.parse() → AudioFrame
    ↓
AudioMixer.push(ssrc, sequence, opus_data)
    ↓
JitterBuffer.push(seq, opus_data) → 重排序/丢包检测
    ↓
OpusDecoder.decode() → PCM
    ↓
AudioMixer._mix_pcm() → 混音
    ↓
AudioPlayer.play() →扬声器输出
 ```

### 5.2 录音识别流程

```
ChannelRecorder (录音完成)
    ↓ on_recording_complete()
RecordingRecognizer.on_recording_complete()
    ↓ 加入识别队列
ThreadPoolExecutor.submit(_process_task)
    ↓
SmartAudioProcessor.process_audio()
    ├─ AudioQualityAnalyzer.analyze() → SNR, RMS
    ├─ DSP (可选)
    ├─ AI 识别 (SenseVoice/Paraformer)
    └─ 信号类型判断 (CQ/QSO/NOISE)
    ↓
Database.update_recording()
    ↓
WxPusher.push() → 微信推送
```

### 5.3 发射音频流程 (PTT)

```
控制台 PTT (空格键按下)
    ↓
AudioRecorder.start_recording()
    ↓
OpusEncoder.encode() → Opus 数据
    ↓
AudioStreamListener.send_audio() → UDP 发送到服务器
    ↓
控制台 PTT (空格键松开)
    ↓
AudioRecorder.stop_recording()
    ↓
on_recording_complete(TX) → 触发识别
```

---

## 六、核心配置参数

### 6.1 音频参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `SAMPLE_RATE` | 48000 Hz | Opus Fullband |
| `FRAME_SIZE` | 960 samples | 20ms @ 48kHz |
| `CHANNELS` | 1 | 单声道 |
| `BITRATE` | 32000 bps | 可调 |
| `PTT_HOLD_TIMEOUT` | 0.30s | 无按键超时 |

### 6.2 缓冲区参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `target_depth` | 3 帧 | 目标缓冲深度 |
| `max_depth` | 50 帧 | 最大缓冲深度 |
| `SILENCE_TIMEOUT` | 0.3s | 用户活跃超时 |
| `STREAM_EXPIRE` | 300s | 流过期时间 |

### 6.3 性能参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `recognizer_workers` | 3 | 识别线程数 |
| `decoder_pool_size` | 5 | 解码器池大小 |
| `metrics_interval` | 60s | 性能报告间隔 |

---

## 七、关键数据结构

### AudioFrame

```python
@dataclass
class AudioFrame:
    user_id: int           # 用户 ID (SSRC)
    sequence: int          # RTP 序列号
    opus_data: bytes       # Opus 编码数据
    is_stop: bool          # 是否为停止帧 (RX_AUDIO_STOP)
    end_marker: bool       # 是否为通话结束标记
    timestamp: float       # 接收时间
```

### Recording 回调

```python
def on_recording_complete(
    filepath: str,           # 录音文件路径
    duration: float,         # 录音时长(秒)
    start_time: str,        # 开始时间
    user_id: str,            # 用户 ID
    user_name: str,         # 用户昵称
    channel_id: int,         # 频道 ID
    recorder_type: str,      # RX/TX
    lost_frames: int,        # 丢包帧数
    loss_rate: float         # 丢包率
)
```

---

## 八、设计模式总结

### 8.1 分层架构
- 每层职责明确，依赖方向单一
- 上层调用下层，下层不能反向调用

### 8.2 事件驱动
- `AudioStreamListener` 通过回调通知
- `ChannelRecorder` 通过回调触发识别
- `RecordingRecognizer` 异步处理

### 8.3 单例模式
- `Database` 类使用单例
- `OpusDecoder` 共享 DLL 句柄

### 8.4 线程池
- 识别器使用 `ThreadPoolExecutor`
- 3 个工作线程并发处理

### 8.5 缓冲池
- 解码器预创建池 (避免首帧延迟)
- JitterBuffer 滑动窗口

---

## 九、总结

BSHT Bot Core 是一个功能完整的 **Ham Radio 辅助系统**，具有以下特点：

| 特性 | 实现 |
|------|------|
| **高内聚低耦合** | 每个模块职责明确，通过回调函数通信 |
| **实时性** | 支持实时语音通信和伪实时识别 |
| **可靠性** | Token 自动刷新、丢包处理(PLC)、重连机制 |
| **可扩展性** | 微信推送、插件化音频处理、多线程并发识别 |
| **性能优化** | 解码器预创建池、异步优化、性能指标监控 |

核心代码约 **8000+ 行 Python**，支持完整的语音通信、录音、AI 识别和微信通知功能。
