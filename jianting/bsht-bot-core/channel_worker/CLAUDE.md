[根目录](../CLAUDE.md) > **channel_worker.py**

---

# 单频道工作线程模块

## 模块职责

单频道监听+录音工作线程，提供独立的频道监听能力。主要特点：
- 纯监听模式：UDP 接收 → Opus 解码 → WAV 录音
- 不需要 PyAudio (不播放不录音)，适合云服务器无声卡环境
- 独立运行，每个 ChannelWorker 有自己的监听器、混音器、录音器

## 入口与启动

```python
from bsht_client import BSHTClient
from channel_worker import ChannelWorker

# 1. 登录客户端
client = BSHTClient()
client.login("username", "password")

# 2. 创建工作线程
worker = ChannelWorker(
    client=client,
    channel_id=62793,
    channel_name="测试频道",
    channel_passcode=0,
    recordings_dir="recordings",
    enable_audio_processing=True,
    headless=True  # 无头模式，不播放音频
)

# 3. 启动
worker.start()

# 4. 停止
worker.stop()
```

## 类接口

### ChannelWorker

```python
worker = ChannelWorker(
    client,              # 已登录的 BSHTClient 实例
    channel_id,          # 频道 ID (int)
    channel_name="",     # 频道显示名 (可选)
    channel_passcode=0,  # 频道密码 (int)
    recordings_dir="recordings",  # 录音目录
    enable_audio_processing=True, # 启用音频预处理
    headless=True        # 无头模式 (不播放音频)
)
```

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `is_running` | bool | 是否正在运行 |
| `channel_id` | int | 频道 ID |
| `channel_name` | str | 频道名称 |

#### 方法

| 方法 | 说明 |
|------|------|
| `start()` | 启动工作线程 |
| `stop()` | 停止工作线程 |

## 核心特性

### 自动重连机制

工作线程内置自动重连：
- 连接失败后 10 秒重试
- 监听器断开后自动重连
- 保活心跳间隔 30 秒

### 成员昵称预加载

启动时自动获取频道成员列表并批量获取昵称：
- 异步后台加载，不阻塞主流程
- 昵称同步到混音器用于录音标记

### 说话者检测

- 精确检测 PTT 按下/松开
- 0.5 秒超时判断停止说话
- 支持多人同时说话

### 录音功能

- 自动按日期分目录存储
- 格式：`序号_用户ID_时间.wav`
- 支持音频预处理 (高通滤波 + AGC)

## 内部组件

```
ChannelWorker
    ├── AudioStreamListener (UDP 监听)
    │       └── AudioMixer (混音 + 解码)
    │               └── JitterBuffer (抖动缓冲)
    └── ChannelRecorder (录音)
            └── AudioProcessor (可选预处理)
```

## 保活循环

工作线程的核心循环，负责：
1. 说话者超时清理
2. 频道状态心跳 (每 30 秒)
3. 监听器状态检查
4. 自动重连触发

```python
# 内部逻辑
while self._is_running:
    # 1. 清理超时说话者 (>0.5s 无音频)
    # 2. 获取频道状态心跳 (每 30s)
    # 3. 检查监听器状态
    # 4. sleep 0.1s
```

## 关键常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `HEARTBEAT_INTERVAL` | 30 | 心跳间隔 (秒) |
| `SPEAKER_TIMEOUT` | 0.5 | 说话者超时 (秒) |

## 依赖项

- `bsht_client.py` - BSHT 客户端和 AudioStreamListener
- `channel_recorder.py` - 频道录音器
- `audio_processor.py` - 音频预处理
- `audio_mixer.py` - 音频混音
- `jitter_buffer.py` - 抖动缓冲

## 使用场景

### 场景1: 单频道监听

```python
client = BSHTClient()
client.login("user", "pass")

worker = ChannelWorker(client, channel_id=12345)
worker.start()

# 监听录音文件
# recordings/2026-02-28/001_userid_time.wav
```

### 场景2: 多频道监听

```python
# 创建多个 worker
workers = []
for ch_id in [12345, 67890, 11111]:
    w = ChannelWorker(client, channel_id=ch_id)
    w.start()
    workers.append(w)

# 停止所有
for w in workers:
    w.stop()
```

### 场景3: 云服务器运行

```python
# headless=True 适合云服务器
worker = ChannelWorker(
    client=client,
    channel_id=12345,
    headless=True  # 不需要音频输出设备
)
```

## 线程安全

- `_user_fetching_lock` - 保护用户信息获取
- 昵称获取异步进行，不阻塞音频处理
- 录音器在混音器就绪后连接

## 常见问题

- **无法加入频道**: 检查频道 ID 和密码是否正确
- **录音器未连接**: 等待混音器初始化 (最多 2.5s)
- **监听器停止**: 自动触发重连

## 相关文件

- `multi_channel_bot.py` - 多频道版本，使用本模块
- `bot_server.py` - 主服务器，使用本模块
- `audio_mixer.py` - 音频混音
- `channel_recorder.py` - 录音器

---

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-02-27 | 创建模块文档 |
