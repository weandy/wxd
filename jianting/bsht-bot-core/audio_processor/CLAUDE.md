[根目录](../CLAUDE.md) > **audio_processor.py**

---

# 音频预处理模块

## 模块职责

对讲机通联场景优化的音频预处理管线，提供：
1. **高通滤波** (80Hz) — 滤除风噪/低频环境噪声
2. **峰值归一化** — 统一音量，解决远/近距离说话音量差异大的问题
3. **AGC 自动增益控制** — 平滑音量变化

## 设计原则

> 录音阶段只做安全的、非破坏性的处理。激进降噪 (RNNoise 等) 放在后处理阶段，避免误删关键通联内容。

## 入口与启动

```python
from audio_processor import AudioProcessor

# 创建处理器
processor = AudioProcessor(sample_rate=48000)

# 处理单帧 PCM (20ms, 960 samples)
processed_pcm = processor.process(raw_pcm_bytes)

# 可选：单独控制处理步骤
processor.enable_highpass = False  # 禁用高通滤波
processor.enable_normalize = False  # 禁用归一化
```

## 核心类

### AudioProcessor

```python
processor = AudioProcessor(
    sample_rate=48000,  # 采样率
    channels=1         # 声道数
)
```

#### 初始化参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `sample_rate` | 48000 | 采样率 (Hz) |
| `channels` | 1 | 声道数 |

#### 属性

| 属性 | 默认值 | 说明 |
|------|--------|------|
| `enable_highpass` | True | 启用高通滤波 |
| `enable_normalize` | True | 启用归一化 |
| `highpass_cutoff` | 80 | 高通截止频率 (Hz) |
| `target_peak_db` | -3.0 | 目标峰值 (dB) |

## 处理算法

### 1. 高通滤波 (High-pass Filter)

**截止频率**: 80Hz

滤除的低频噪声：
- 风噪 (20-60Hz)
- 机械振动 (30-80Hz)
- 电源哼声 (50/60Hz)

**算法**: 一阶 RC 高通滤波器

```
y[n] = α * (y[n-1] + x[n] - x[n-1])
```

### 2. AGC 归一化 (Automatic Gain Control)

**目标峰值**: -3.0 dB

**增益控制**:
- 快速降低增益 (attack): 0.01 — 防削顶
- 缓慢提升增益 (release): 0.001 — 避免噪声放大
- 最大增益: 10.0
- 最小增益: 0.1

## 处理流程

```
原始 PCM (16-bit, little-endian)
    ↓
1. 高通滤波 (可选)
   - 滤除 < 80Hz 低频
    ↓
2. AGC 归一化 (可选)
   - 平滑音量到目标峰值
    ↓
3. 裁剪
   - 限制在 int16 范围
    ↓
处理后 PCM
```

## 使用场景

### 场景1: 录音预处理

```python
from channel_recorder import ChannelRecorder
from audio_processor import AudioProcessor

# 创建音频预处理器
processor = AudioProcessor(sample_rate=48000)

# 创建录音器时传入
recorder = ChannelRecorder(
    base_dir="recordings",
    channel_id=12345,
    recorder_type="RX",
    audio_processor=processor
)
```

### 场景2: ChannelWorker 中使用

```python
from channel_worker import ChannelWorker

# 自动启用音频处理
worker = ChannelWorker(
    client=client,
    channel_id=12345,
    enable_audio_processing=True  # 默认启用
)
```

### 场景3: 禁用特定处理

```python
processor = AudioProcessor(sample_rate=48000)

# 只保留高通滤波，禁用归一化
processor.enable_normalize = False
```

## 依赖项

- `numpy` - 数值计算

## 参数调优

### 高通截止频率

| 场景 | 推荐值 |
|------|--------|
| 室内安静环境 | 60 Hz |
| 户外有风 | 100 Hz |
| 默认 | 80 Hz |

### 目标峰值

| 场景 | 推荐值 |
|------|--------|
| 语音为主 | -3.0 dB |
| 音乐为主 | -1.0 dB |
| 保守处理 | -6.0 dB |

## 注意事项

1. **状态保持**: 滤波器保持状态，跨帧连续处理
2. **实时处理**: 专为实时音频流设计，每帧独立处理
3. **非破坏性**: 不删除任何音频数据，只调整电平

## 相关文件

- `channel_worker.py` - 使用本模块进行录音预处理
- `channel_recorder.py` - 录音器集成
- `src/smart_processor.py` - 后处理阶段的 DSP

---

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-02-27 | 创建模块文档 |
