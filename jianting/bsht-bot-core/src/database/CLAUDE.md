[根目录](../CLAUDE.md) > [src/](../) > **database.py**

---

# 数据库模块

## 模块职责

SQLite 数据库模块，用于存储音频识别结果和录音记录。支持线程安全的同步/异步操作。

## 入口与启动

```python
from database import get_database, AudioRecord, Recording

# 获取数据库实例
db = get_database("data/records.db")

# 添加录音记录
recording = Recording(
    filepath="/path/to/audio.wav",
    channel_id=123,
    user_id="user123",
    duration=10.5
)
db.add_recording(recording)

# 添加识别记录
record = AudioRecord(
    timestamp="2026-02-27 10:00:00",
    channel_id=123,
    user_id=456,
    content="识别文本"
)
db.add_record(record)

# 查询记录
recordings = db.get_recordings(limit=100)
```

## 对外接口

### Database
- `add_recording(recording)` - 添加录音记录
- `add_record(record)` - 添加识别记录
- `get_recordings(limit, offset)` - 获取录音列表
- `get_records(limit, offset)` - 获取识别记录列表
- `update_recording(id, **kwargs)` - 更新录音记录
- `search_records(keyword)` - 搜索识别记录

## 数据模型

### AudioRecord (音频识别记录)
```python
@dataclass
class AudioRecord:
    id: Optional[int]
    timestamp: str
    channel_id: int
    user_id: int
    nickname: str

    # 音频质量
    rms_db: float
    peak_db: float
    noise_db: float
    snr_db: float

    # DSP 处理
    dsp_needed: bool
    dsp_algorithm: str
    dsp_applied: bool

    # 识别结果
    signal_type: str  # CQ, QSO, NOISE, UNKNOWN
    content: str
    content_normalized: str
    confidence: float

    # 元数据
    duration: float
    audio_path: str
```

### Recording (录音记录)
```python
@dataclass
class Recording:
    id: Optional[int]
    filepath: str
    filename: str
    channel_id: int
    user_id: str          # SSRC
    user_name: str        # 用户昵称
    recorder_type: str    # RX/TX
    duration: float       # 秒
    start_time: str       # 精确到0.1秒
    file_size: int
    timestamp: str

    # 识别状态
    recognized: bool
    asr_text: str
    content_normalized: str
    signal_type: str
    confidence: float

    # 音频质量
    rms_db: float
    snr_db: float

    # 识别耗时
    recognize_duration: float
```

## 常见问题

- **数据库路径**: 默认 `data/records.db`
- **线程安全**: 支持多线程访问
- **异步支持**: 可通过 `async_database_wrapper` 使用异步操作

## 相关文件

- `src/main.py` - 使用本模块的主入口
- `src/recognizer.py` - 调用本模块存储识别结果

---

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-02-27 | 创建模块文档 |
