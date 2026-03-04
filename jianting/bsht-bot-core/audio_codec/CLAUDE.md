[根目录](../CLAUDE.md) > [Python 根目录](../) > **audio_codec.py**

---

# Audio Codec 模块

## 模块职责

音频编解码模块，实现 Opus 编解码器封装、音频采集器、播放器和 PTT 控制器。

## 入口与启动

```python
from audio_codec import AudioCodec, AudioRecorder, AudioPlayer, PTTController

# 创建编解码器
codec = AudioCodec()

# 创建音频播放器
player = AudioPlayer()
player.start()

# 创建录音器
recorder = AudioRecorder(on_audio_callback)
recorder.start()

# PTT 控制
ptt = PTTController()
ptt.start()
```

## 对外接口

### AudioCodec
- `encode(pcm_data)` - Opus 编码
- `decode(opus_data)` - Opus 解码
- `get_supported_sizes()` - 获取支持的帧大小

### AudioRecorder
- `start()` - 开始录音
- `stop()` - 停止录音
- `get_audio_level()` - 获取当前音频电平
- `is_speaking()` - 检测是否在说话

### AudioPlayer
- `play(pcm_data)` - 播放 PCM 数据
- `play_opus(opus_data)` - 播放 Opus 数据
- `set_volume(volume)` - 设置音量 (0.0-1.0)
- `mute()` / `unmute()` - 静音控制

### PTTController
- `start()` - 启动 PTT 监听
- `stop()` - 停止 PTT 监听
- `is_ptt_pressed()` - 获取 PTT 状态

## 关键依赖

- `numpy` - 音频数据处理
- `pyaudio` - 音频设备访问
- `async_optimization` - 异步优化

## 重要常量

```python
SAMPLE_RATE = 48000      # Opus Fullband
FRAME_SIZE = 960         # 20ms @ 48kHz
CHANNELS = 1             # 单声道
PTT_HOLD_TIMEOUT = 0.30  # 300ms 无按键 = 松开
```

## 常见问题

- **音频设备**: 确保系统安装了 PortAudio 库
- **PTT 按键**: 空格键为默认 PTT 按键，Q 键退出
- **异步优化**: 模块优先使用 `async_optimization` 的线程池

## 相关文件

- `bot_server.py` - 使用本模块的服务器实现
- `jitter_buffer.py` - 抖动缓冲（配合使用）
- `audio_mixer.py` - 音频混音（配合使用）

---

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-02-27 | 创建模块文档 |
