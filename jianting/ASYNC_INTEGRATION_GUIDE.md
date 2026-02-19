# 异步优化集成指南

> 本指南说明如何将异步优化集成到现有代码中
> 基于渐进式优化策略，保持向后兼容

---

## 📦 新增模块

### 1. async_optimization.py - 核心优化模块

```python
from async_optimization import (
    get_metrics_collector,    # 性能指标收集
    get_thread_pool,          # 线程池管理
    get_optimizer,            # 性能优化器
    timed_sync,               # 同步函数计时装饰器
    run_in_pool               # 线程池执行装饰器
)
```

### 2. async_database_wrapper.py - 数据库异步包装器

```python
from async_database_wrapper import get_async_database
```

---

## 🚀 快速集成

### 1. 添加性能指标收集

在 `bot_server.py` 或 `bsht_client.py` 中添加：

```python
# 在文件开头导入
from async_optimization import get_metrics_collector

# 获取指标收集器
metrics = get_metrics_collector()

# 在关键位置记录指标
def some_function():
    start = time.time()
    try:
        # 原有逻辑
        result = do_something()
        return result
    finally:
        duration = time.time() - start
        metrics.record("some_function", duration, error=False)
```

### 2. 使用线程池处理CPU密集型任务

```python
from async_optimization import get_thread_pool

# 原来的代码 (阻塞)
def process_audio(data):
    # CPU密集型处理
    result = heavy_processing(data)
    return result

# 优化后 (不阻塞主线程)
def process_audio_async(data):
    pool = get_thread_pool()
    # 提交到线程池，立即返回
    future = pool.submit_cpu(heavy_processing, data)
    return future  # 返回 Future 对象

# 或者使用装饰器
from async_optimization import run_in_pool

@run_in_pool(pool_type="cpu")
def process_audio(data):
    return heavy_processing(data)
```

### 3. 异步数据库操作

```python
# 原来的同步代码
def save_recording(recording):
    db.add_recording(recording)  # 阻塞

# 优化后 (异步)
import asyncio

async def save_recording_async(recording):
    from async_database_wrapper import get_async_database
    from src.database import get_database

    # 获取异步包装器
    db = get_database()
    async_db = get_async_database(db)

    # 异步添加
    await async_db.add_recording(recording)

# 或者批量更新
async def batch_update_recognitions(updates):
    async_db = get_async_database(get_database())
    count = await async_db.batch_update(updates)
    return count
```

### 4. 使用异步HTTP客户端

```python
import asyncio
from async_optimization import AsyncHttpClient

async def send_webhook(data):
    client = AsyncHttpClient()

    try:
        result = await client.post(
            "https://example.com/webhook",
            json=data
        )
        return result
    finally:
        await client.close()
```

---

## 📊 性能监控

### 查看性能指标

在程序中添加定期打印：

```python
import threading
import time

def metrics_reporter(interval=60):
    """定期报告性能指标"""
    metrics = get_metrics_collector()

    while True:
        time.sleep(interval)
        metrics.print_summary()

# 启动报告线程
reporter = threading.Thread(target=metrics_reporter, daemon=True)
reporter.start()
```

### 监控关键指标

| 指标 | 正常范围 | 告警阈值 |
|------|---------|----------|
| http.get | < 100ms | > 500ms |
| http.post | < 200ms | > 1000ms |
| database.query | < 50ms | > 200ms |
| audio.process | < 20ms | > 100ms |

---

## 🔧 逐步集成计划

### 第一阶段: 指标收集 (1-2小时)

1. 在关键函数添加指标记录
2. 观察性能基线

```python
# 示例: 在 bot_server.py 中
def some_function():
    metrics = get_metrics_collector()
    start = time.time()

    try:
        # 原有代码
        result = do_something()
        return result
    finally:
        metrics.record("some_function", time.time() - start)
```

### 第二阶段: 线程池优化 (2-4小时)

1. 识别CPU密集型任务
2. 使用线程池处理

```python
# 示例: 在音频处理中
from async_optimization import get_thread_pool

def process_audio_frame(data):
    # 原来的CPU密集型处理
    return heavy_processing(data)

# 优化后
pool = get_thread_pool()
future = pool.submit_cpu(process_audio_frame, data)
result = future.result()  # 或异步等待
```

### 第三阶段: 数据库异步化 (2-3小时)

1. 替换阻塞的数据库操作
2. 添加批量操作

```python
# 示例: 在 recognizer.py 中
async def on_recording_complete(recording):
    async_db = get_async_database(get_database())

    # 异步添加到数据库
    await async_db.add_recording(recording)

    # 异步更新识别结果
    await async_db.update_recognition(
        filepath=recording['filepath'],
        asr_text=result.text,
        signal_type=result.type,
        confidence=result.confidence
    )
```

---

## ⚠️ 注意事项

### 1. 线程安全

- 共享状态需要加锁
- 优先使用队列进行线程间通信
- 避免死锁

### 2. 异常处理

- 异步代码中正确处理异常
- 使用 try/finally 确保资源释放

### 3. 性能监控

- 不要过度记录指标 (开销)
- 关注关键路径的性能

### 4. 向后兼容

- 保持原有API不变
- 新增异步版本，不删除同步版本

---

## 📝 完整示例

### 在 bot_server.py 中集成

```python
import time
import threading
from async_optimization import (
    get_metrics_collector,
    get_thread_pool,
    timed_sync
)

# 在 BotServer 类中添加
class BotServer:
    def __init__(self, ...):
        # ... 原有初始化 ...

        # 添加性能指标收集
        self.metrics = get_metrics_collector()
        self.thread_pool = get_thread_pool()

        # 启动性能报告线程
        self._start_metrics_reporter()

    def _start_metrics_reporter(self):
        """启动性能报告线程"""
        def reporter():
            while True:
                time.sleep(60)  # 每分钟报告
                self.metrics.print_summary()

        t = threading.Thread(target=reporter, daemon=True)
        t.start()

    # 使用计时装饰器
    @timed_sync("bot_server.login")
    def _login(self) -> bool:
        # 原有登录逻辑
        ...

    @timed_sync("bot_server.join_channel")
    def _join_channel(self) -> bool:
        # 原有加入频道逻辑
        ...

    # 使用线程池处理CPU密集型任务
    def _process_audio_background(self, data):
        # 提交到线程池
        future = self.thread_pool.submit_cpu(
            self._heavy_audio_processing,
            data
        )
        return future

    def _heavy_audio_processing(self, data):
        # CPU密集型处理
        ...
```

---

## ✅ 检查清单

- [ ] 导入 async_optimization 模块
- [ ] 在关键函数添加指标记录
- [ ] 识别CPU密集型任务并使用线程池
- [ ] 异步化数据库操作 (可选)
- [ ] 添加性能监控输出
- [ ] 测试并验证性能提升
- [ ] 更新文档

---

## 📚 参考资料

- `DETAILED_ASYNC_IO_GUIDE.md` - 详细的异步I/O方案
- `src/database_pool.py` - 数据库连接池
- `src/error_handling.py` - 错误处理工具
