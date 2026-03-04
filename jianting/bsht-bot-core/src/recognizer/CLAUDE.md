[根目录](../CLAUDE.md) > [src/](../) > **recognizer.py**

---

# 语音识别器模块

## 模块职责

伪实时识别器，监听录音完成事件并调用 SiliconFlow API 进行语音识别。支持并发识别、音频质量分析和微信推送。

## 入口与启动

```python
from recognizer import RecordingRecognizer

# 创建识别器
recognizer = RecordingRecognizer(api_key="your-api-key")

# 设置数据库和推送器
recognizer.set_database(db)
recognizer.set_pusher(pusher)

# 添加待识别文件
recognizer.add_file(audio_file_path, metadata)

# 启动识别器
recognizer.start()

# 关闭识别器
recognizer.shutdown()
```

## 对外接口

### RecordingRecognizer
- `set_database(db)` - 设置数据库实例
- `set_pusher(pusher)` - 设置微信推送器
- `add_file(file_path, metadata)` - 添加待识别文件到队列
- `get_pending_count()` - 获取待处理数量
- `start()` - 启动识别器
- `shutdown(wait=True)` - 关闭识别器

## 关键依赖

- `src/smart_processor.py` - 音频处理
- `src/wx_pusher.py` - 微信推送
- `src/database.py` - 数据存储
- `httpx` - HTTP 客户端

## 配置项

```python
# 并发识别配置
max_workers = 3  # 线程池工作线程数
```

## 工作流程

1. 录音文件生成完成事件触发
2. 文件添加到待识别队列
3. 线程池并发处理识别任务
4. 调用 SiliconFlow Paraformer 模型
5. 音频质量分析 (DSP)
6. 保存识别结果到数据库
7. 根据关键词推送到微信

## 常见问题

- **并发限制**: 默认 3 个并发识别任务
- **API 密钥**: 需要配置 `SILICONFLOW_API_KEY`
- **识别队列**: 使用线程安全的队列管理

## 相关文件

- `src/main.py` - 使用本模块的主入口
- `src/smart_processor.py` - 音频处理
- `src/wx_pusher.py` - 消息推送
- `src/database.py` - 数据持久化

---

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-02-27 | 创建模块文档 |
