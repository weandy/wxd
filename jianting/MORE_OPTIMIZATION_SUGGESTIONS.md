# 更多优化建议

> 基于已修复5个关键问题后的进一步优化建议
> 生成时间: 2026-02-19
> 当前版本: main branch (commit 0843094)

---

## 📋 优化概览

在已修复SQL注入、竞态条件、资源泄漏、错误处理和连接池问题后，仍然存在以下可以优化的方面：

| 类别 | 优化项 | 优先级 | 预期收益 |
|------|--------|--------|----------|
| 架构 | 模块重构 | 中 | 提升可维护性 |
| 性能 | 缓存机制 | 中 | 减少重复计算 |
| 性能 | 异步I/O | 高 | 显著提升响应速度 |
| 安全 | API密钥加密 | 高 | 提升安全性 |
| 质量 | 单元测试 | 高 | 提升代码质量 |
| 质量 | 类型注解 | 中 | 提升IDE支持 |
| 运维 | 监控告警 | 中 | 提升可观测性 |
| 文档 | API文档 | 低 | 提升开发体验 |

---

## 🏗️ 1. 架构优化

### 1.1 模块化重构

**当前问题**:
```python
# bsht_client.py - 2355行，过于庞大
# bot_server.py - 706行，职责混杂
# src/smart_processor.py - 1037行，功能复杂
```

**建议结构**:
```
bsht_bot/
├── core/                    # 核心功能
│   ├── __init__.py
│   ├── client.py            # gRPC客户端 (拆分bsht_client)
│   ├── protocol/            # 协议处理
│   │   ├── rtp.py
│   │   ├── heartbeat.py
│   │   └── binary.py
│   └── audio/               # 音频处理
│       ├── codec.py         # 编解码
│       ├── mixer.py         # 混音
│       ├── recorder.py      # 录音
│       └── processor.py     # 预处理
│
├── services/                # 业务服务
│   ├── __init__.py
│   ├── recognition.py       # 语音识别
│   ├── database.py          # 数据库
│   ├── pusher.py            # 微信推送
│   └── config.py            # 配置管理
│
├── api/                     # API层
│   ├── __init__.py
│   └── endpoints.py         # REST API (如果需要)
│
├── utils/                   # 工具函数
│   ├── __init__.py
│   ├── logger.py            # 日志工具
│   ├── validators.py        # 验证器
│   └── decorators.py        # 装饰器
│
├── server.py                # 服务器入口
└── main.py                  # 命令行入口
```

**拆分示例**:
```python
# bsht_client.py 拆分为:
# - core/client.py - 基础gRPC客户端
# - core/audio/transmitter.py - 发射功能
# - core/audio/receiver.py - 接收功能
# - core/auth.py - 认证和token管理

# core/client.py
class BSHTClient:
    """简化的客户端，只负责基础通信"""
    def __init__(self, config: ClientConfig):
        self.config = config
        self.channel = grpc.insecure_channel(config.server)
        self.auth = AuthManager(config)

# core/audio/transmitter.py
class AudioTransmitter:
    """音频发射器 - 从bsht_client.py拆分"""
    def __init__(self, client: BSHTClient):
        self.client = client
        self.state = TransmitState.IDLE

    def start(self):
        """开始发射"""
        ...

# core/auth.py
class AuthManager:
    """认证管理器 - 从bsht_client.py拆分"""
    def __init__(self, config: ClientConfig):
        self.config = config
        self.token = None

    def login(self) -> Token:
        """登录"""
        ...
```

---

## ⚡ 2. 性能优化

### 2.1 实现缓存机制

**当前问题**:
```python
# src/recognizer.py - 每次都查询数据库
def on_recording_complete(self, filepath: str, ...):
    if self._db:
        existing = self._db.get_recording_by_path(filepath)  # ⚠️ 无缓存
```

**优化方案**:
```python
# utils/cache.py - 新建文件
import functools
import hashlib
import pickle
import time
from typing import Any, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class TTLCache:
    """带TTL的缓存"""

    def __init__(self, ttl: int = 3600, max_size: int = 1000):
        """
        Args:
            ttl: 缓存生存时间(秒)
            max_size: 最大缓存条目数
        """
        self.ttl = ttl
        self.max_size = max_size
        self._cache = {}
        self._timestamps = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        with self._lock:
            if key not in self._cache:
                return None

            # 检查是否过期
            if time.time() - self._timestamps[key] > self.ttl:
                del self._cache[key]
                del self._timestamps[key]
                return None

            return self._cache[key]

    def set(self, key: str, value: Any):
        """设置缓存"""
        with self._lock:
            # LRU淘汰
            if len(self._cache) >= self.max_size:
                oldest = min(self._timestamps, key=self._timestamps.get)
                del self._cache[oldest]
                del self._timestamps[oldest]

            self._cache[key] = value
            self._timestamps[key] = time.time()

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()


def cached(ttl: int = 3600, key_func: Optional[Callable] = None):
    """缓存装饰器

    Usage:
        @cached(ttl=600, key_func=lambda filepath: filepath)
        def get_recording(filepath):
            return db.query(filepath)
    """
    cache = TTLCache(ttl=ttl)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{args}:{kwargs}"

            # 尝试从缓存获取
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return cached_value

            # 调用函数
            result = func(*args, **kwargs)

            # 存入缓存
            cache.set(cache_key, result)
            return result

        return wrapper

    return decorator


# 使用示例
class DatabaseWithCache:
    def __init__(self):
        self._recording_cache = TTLCache(ttl=600, max_size=1000)

    @cached(ttl=600)
    def get_recording_by_path(self, filepath: str):
        """带缓存的查询"""
        return self.conn.execute(
            "SELECT * FROM recordings WHERE filepath=?",
            (filepath,)
        ).fetchone()
```

### 2.2 异步I/O优化

**当前问题**:
```python
# bot_server.py - 阻塞式I/O
def _audio_receive_loop(self):
    while self._is_listening:
        data, addr = self.udp_socket.recvfrom(2048)  # ⚠️ 阻塞
        self.process_audio(data)
```

**优化方案**:
```python
# async_server.py - 新建文件
import asyncio
import logging

logger = logging.getLogger(__name__)


class AsyncAudioServer:
    """异步音频服务器"""

    def __init__(self, host: str = "0.0.0.0", port: int = 0):
        self.host = host
        self.port = port
        self.transport = None
        self.protocol = None

    async def start(self):
        """启动异步服务器"""
        loop = asyncio.get_event_loop()

        # 创建UDP endpoint
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: AudioProtocol(),
            local_addr=(self.host, self.port)
        )

        logger.info(f"[AsyncServer] 监听: {self.host}:{self.port}")

        # 获取实际端口
        self.port = self.transport.get_extra_info('sockname')[1]
        return self.port

    async def stop(self):
        """停止服务器"""
        if self.transport:
            self.transport.close()


class AudioProtocol(asyncio.DatagramProtocol):
    """异步音频协议"""

    def __init__(self):
        self.transport = None
        self.mixer = None  # AudioMixer实例

    def connection_made(self, transport):
        self.transport = transport
        logger.info("[AudioProtocol] 连接建立")

    def datagram_received(self, data, addr):
        """接收数据报 (异步)"""
        try:
            # 非阻塞处理
            asyncio.create_task(self.process_audio(data, addr))
        except Exception as e:
            logger.error(f"处理音频失败: {e}")

    async def process_audio(self, data: bytes, addr: tuple):
        """异步处理音频"""
        # 解析RTP
        rtp_packet = parse_rtp(data)

        # 推送到混音器 (非阻塞)
        if self.mixer:
            self.mixer.push(
                ssrc=rtp_packet.ssrc,
                sequence=rtp_packet.sequence,
                opus_data=rtp_packet.payload,
                marker=rtp_packet.marker
            )


# 使用示例
async def main():
    server = AsyncAudioServer()
    await server.start()

    try:
        # 运行其他任务
        await asyncio.sleep(3600)  # 运行1小时
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 🔐 3. 安全优化

### 3.1 API密钥加密存储

**当前问题**:
```python
# .env文件 - 明文存储
SILICONFLOW_API_KEY=sk-grfgzzbhvatgwrdmdnqyxatbfyctrqmnmuhukrrhxusofidj
```

**优化方案**:
```python
# utils/encryption.py - 新建文件
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
import logging

logger = logging.getLogger(__name__)


class SecretManager:
    """密钥管理器"""

    def __init__(self, master_key: Optional[bytes] = None):
        """
        Args:
            master_key: 主密钥，如果不提供则从环境变量获取
        """
        if master_key is None:
            master_key = os.getenv("MASTER_KEY", "").encode()

        if not master_key:
            # 从机器特征生成密钥
            import uuid
            machine_id = str(uuid.getnode())
            master_key = machine_id.encode()

        # 派生加密密钥
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"bsht_bot_salt",  # 生产环境应随机生成
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key))
        self.cipher = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """加密"""
        encrypted = self.cipher.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt(self, ciphertext: str) -> str:
        """解密"""
        encrypted = base64.urlsafe_b64decode(ciphertext.encode())
        decrypted = self.cipher.decrypt(encrypted)
        return decrypted.decode()

    def encrypt_api_key(self, api_key: str) -> str:
        """加密API密钥"""
        return self.encrypt(api_key)

    def get_api_key(self, encrypted_key: str) -> str:
        """获取解密后的API密钥"""
        return self.decrypt(encrypted_key)


# 使用示例
# 1. 首次使用: 加密API密钥
manager = SecretManager()
encrypted = manager.encrypt_api_key("sk-xxxxx")
print(f"加密后的密钥: {encrypted}")

# 2. 存储到 .env
# API_KEY_ENCRYPTED=gAAAAABl...

# 3. 运行时解密
api_key = manager.get_api_key(os.getenv("API_KEY_ENCRYPTED"))
```

### 3.2 请求签名验证

**优化方案**:
```python
# utils/signature.py - 新建文件
import hmac
import hashlib
import time
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class RequestSigner:
    """请求签名器"""

    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode()

    def sign(self, data: Dict) -> str:
        """生成签名"""
        # 添加时间戳
        data['timestamp'] = int(time.time())

        # 按key排序
        sorted_items = sorted(data.items())

        # 拼接字符串
        sign_str = '&'.join([f"{k}={v}" for k, v in sorted_items])

        # HMAC-SHA256
        signature = hmac.new(
            self.secret_key,
            sign_str.encode(),
            hashlib.sha256
        ).hexdigest()

        return signature

    def verify(self, data: Dict, signature: str) -> bool:
        """验证签名"""
        expected = self.sign(data)
        return hmac.compare_digest(expected, signature)


# 使用示例
signer = RequestSigner("my_secret_key")

# 发送请求时
data = {"user_id": 123, "action": "transmit"}
signature = signer.sign(data)
request_data = {**data, "signature": signature}

# 验证请求时
is_valid = signer.verify(data, signature)
```

---

## 🧪 4. 测试优化

### 4.1 增加单元测试覆盖率

**当前问题**:
```python
# tests/test_fixes.py - 只有13个测试
# 大部分核心代码没有测试
```

**优化方案**:
```python
# tests/test_audio_processor.py - 新建文件
import pytest
import numpy as np
from audio_processor import AudioProcessor


class TestAudioProcessor:
    """音频处理器测试"""

    def test_highpass_filter(self):
        """测试高通滤波"""
        processor = AudioProcessor(sample_rate=48000)
        processor.enable_highpass = True
        processor.enable_normalize = False

        # 生成低频信号 (50Hz)
        duration = 1.0
        sample_rate = 48000
        t = np.linspace(0, duration, int(sample_rate * duration))
        low_freq_signal = np.sin(2 * np.pi * 50 * t)
        low_freq_pcm = (low_freq_signal * 32767).astype(np.int16).tobytes()

        # 处理
        processed = processor.process(low_freq_pcm)

        # 验证: 低频应该被衰减
        processed_samples = np.frombuffer(processed, dtype=np.int16)
        assert np.abs(processed_samples).max() < 1000  # 应该被大幅衰减

    def test_normalize(self):
        """测试归一化"""
        processor = AudioProcessor()
        processor.enable_highpass = False
        processor.enable_normalize = True

        # 生成小信号
        small_signal = np.ones(960, dtype=np.int16) * 100
        small_pcm = small_signal.tobytes()

        # 处理
        processed = processor.process(small_pcm)
        processed_samples = np.frombuffer(processed, dtype=np.int16)

        # 验证: 应该被放大
        assert np.abs(processed_samples).max() > 1000


# tests/test_smart_processor.py - 新建文件
class TestSmartProcessor:
    """智能处理器测试"""

    @pytest.fixture
    def processor(self):
        from src.smart_processor import SmartAudioProcessor
        return SmartAudioProcessor(api_key="test")

    def test_audio_quality_analysis(self, processor):
        """测试音频质量分析"""
        # 生成测试音频
        import wave
        test_file = "test_audio.wav"

        with wave.open(test_file, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            # 生成1秒的正弦波
            samples = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 48000))
            wf.writeframes((samples * 32767).astype(np.int16).tobytes())

        # 分析
        quality = processor._analyze_audio_quality(test_file)

        assert quality.snr_db > 0
        assert quality.duration == 1.0

        # 清理
        os.remove(test_file)
```

### 4.2 集成测试

**优化方案**:
```python
# tests/integration/test_full_pipeline.py - 新建文件
import pytest
import asyncio
from bsht_client import BSHTClient
from audio_mixer import AudioMixer
from channel_recorder import ChannelRecorder


@pytest.mark.integration
class TestFullPipeline:
    """完整流程集成测试"""

    @pytest.fixture
    async def client(self):
        """测试客户端"""
        config = {
            "username": "test_user",
            "password": "test_pass",
            "channel_id": 12345
        }
        client = BSHTClient(config)
        yield client
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_audio_receive_pipeline(self, client):
        """测试音频接收流程"""
        # 连接
        await client.connect()

        # 加入频道
        await client.join_channel(12345)

        # 接收音频
        mixer = AudioMixer()
        recorder = ChannelRecorder(channel_id=12345)
        mixer.set_recorder(recorder)

        # 模拟接收RTP包
        test_packets = generate_test_rtp_packets(count=10)
        for packet in test_packets:
            mixer.push(
                ssrc=packet.ssrc,
                sequence=packet.sequence,
                opus_data=packet.payload,
                marker=packet.marker
            )

        # 验证录音
        assert recorder._active[packet.ssrc] is not None
```

---

## 📊 5. 监控和日志优化

### 5.1 结构化日志

**当前问题**:
```python
# 混乱的日志格式
logger.info(f"[TX] 开始发射")
logger.info("[TX] 🟢 开始发射")
logger.info(f"识别完成: {os.path.basename(filepath)}")
```

**优化方案**:
```python
# utils/structured_logger.py - 新建文件
import logging
import json
from typing import Dict, Any
from datetime import datetime


class StructuredLogger:
    """结构化日志记录器"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def log(self, level: str, event: str, **kwargs):
        """记录结构化日志

        Args:
            level: 日志级别 (INFO, WARNING, ERROR)
            event: 事件名称
            **kwargs: 额外字段
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "event": event,
            **kwargs
        }

        # 格式化输出
        message = json.dumps(log_data, ensure_ascii=False)

        # 记录
        log_func = getattr(self.logger, level.lower())
        log_func(message)

    def info(self, event: str, **kwargs):
        """INFO级别"""
        self.log("INFO", event, **kwargs)

    def warning(self, event: str, **kwargs):
        """WARNING级别"""
        self.log("WARNING", event, **kwargs)

    def error(self, event: str, **kwargs):
        """ERROR级别"""
        self.log("ERROR", event, **kwargs)


# 使用示例
logger = StructuredLogger("audio")

# 记录事件
logger.info("transmit_start", user_id=123, channel_id=456)
# {"timestamp": "2026-02-19T...", "level": "INFO", "event": "transmit_start", "user_id": 123, "channel_id": 456}

logger.error("transmit_failed", user_id=123, error="Connection timeout")
# {"timestamp": "2026-02-19T...", "level": "ERROR", "event": "transmit_failed", "user_id": 123, "error": "Connection timeout"}
```

### 5.2 性能监控

**优化方案**:
```python
# utils/metrics.py - 新建文件
import time
import threading
from typing import Dict, List
from collections import deque
import logging

logger = logging.getLogger(__name__)


class MetricsCollector:
    """性能指标收集器"""

    def __init__(self, window_size: int = 100):
        """
        Args:
            window_size: 滑动窗口大小
        """
        self.window_size = window_size
        self._metrics = {}
        self._lock = threading.Lock()

    def record(self, name: str, value: float, tags: Dict = None):
        """记录指标

        Args:
            name: 指标名称
            value: 指标值
            tags: 标签 (用于分组)
        """
        with self._lock:
            key = f"{name}:{tags}" if tags else name

            if key not in self._metrics:
                self._metrics[key] = {
                    'name': name,
                    'tags': tags or {},
                    'values': deque(maxlen=self.window_size)
                }

            self._metrics[key]['values'].append(value)

    def get_stats(self, name: str, tags: Dict = None) -> Dict:
        """获取统计信息

        Returns:
            {'min': 最小值, 'max': 最大值, 'avg': 平均值, 'count': 样本数}
        """
        with self._lock:
            key = f"{name}:{tags}" if tags else name

            if key not in self._metrics:
                return {}

            values = list(self._metrics[key]['values'])

            if not values:
                return {}

            return {
                'min': min(values),
                'max': max(values),
                'avg': sum(values) / len(values),
                'count': len(values),
                'p50': sorted(values)[len(values) // 2],
                'p95': sorted(values)[int(len(values) * 0.95)] if len(values) > 20 else values[-1],
                'p99': sorted(values)[int(len(values) * 0.99)] if len(values) > 100 else values[-1],
            }

    def get_all_metrics(self) -> List[Dict]:
        """获取所有指标"""
        with self._lock:
            return [
                {
                    'name': m['name'],
                    'tags': m['tags'],
                    'stats': self.get_stats(m['name'], m['tags'])
                }
                for m in self._metrics.values()
            ]


# 全局指标收集器
metrics = MetricsCollector()


def timed(metric_name: str, tags: Dict = None):
    """计时装饰器

    Usage:
        @timed("audio_process", {"codec": "opus"})
        def process_audio(data):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                metrics.record(metric_name, duration, tags)
        return wrapper
    return decorator


# 使用示例
@timed("audio_decode", {"codec": "opus"})
def decode_opus(data: bytes):
    ...

# 每60秒打印一次统计
def print_metrics():
    import asyncio

    async def metrics_reporter():
        while True:
            await asyncio.sleep(60)
            for m in metrics.get_all_metrics():
                logger.info(
                    f"Metric: {m['name']}",
                    tags=m['tags'],
                    stats=m['stats']
                )

    asyncio.create_task(metrics_reporter())
```

---

## 📝 6. 类型注解

**当前问题**:
```python
# 大部分函数缺少类型注解
def start_transmit(self) -> bool:  # ✅ 有返回类型
def push(self, ssrc, sequence, opus_data, marker=False):  # ❌ 缺少类型
```

**优化方案**:
```python
# 添加类型注解
from typing import Optional, List, Dict, Tuple, Callable
from dataclasses import dataclass
import numpy as np


@dataclass
class RTPPacket:
    """RTP包"""
    ssrc: int
    sequence: int
    timestamp: int
    marker: bool
    payload: bytes


def push(
    self,
    ssrc: int,
    sequence: int,
    opus_data: bytes,
    marker: bool = False
) -> None:
    """推送RTP包到混音器

    Args:
        ssrc: 用户标识
        sequence: 序列号
        opus_data: Opus编码数据
        marker: RTP Marker位

    Returns:
        None
    """
    ...


def pop_mixed(self) -> Optional[bytes]:
    """获取混音后的PCM数据

    Returns:
        混音后的PCM数据，如果没有活跃用户则返回None
    """
    ...


# 类型检查
# mypy bsht_client.py --strict
```

---

## 🚀 7. 部署优化

### 7.1 Docker容器化

**优化方案**:
```dockerfile
# Dockerfile - 新建文件
FROM python:3.9-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    libopus0 \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["python", "server.py"]
```

### 7.2 配置管理

**优化方案**:
```yaml
# docker-compose.yml - 新建文件
version: '3.8'

services:
  bsht-bot:
    build: .
    container_name: bsht-bot
    restart: unless-stopped
    environment:
      - BSHT_USERNAME=${BSHT_USERNAME}
      - BSHT_PASSWORD=${BSHT_PASSWORD}
      - BSHT_CHANNEL_ID=${BSHT_CHANNEL_ID}
      - SILICONFLOW_API_KEY=${SILICONFLOW_API_KEY}
      - DATABASE_PATH=/data/records.db
    volumes:
      - ./recordings:/app/recordings
      - ./data:/data
      - ./logs:/app/logs
    ports:
      - "8000:8000"
    networks:
      - bsht-network

  # 可选: PostgreSQL数据库
  postgres:
    image: postgres:14
    container_name: bsht-db
    restart: unless-stopped
    environment:
      - POSTGRES_DB=bsht
      - POSTGRES_USER=bsht
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - bsht-network

networks:
  bsht-network:
    driver: bridge

volumes:
  postgres_data:
```

---

## 📖 8. 文档优化

### 8.1 API文档生成

**优化方案**:
```python
# 使用Sphinx生成API文档

# docs/conf.py - 新建文件
import os
import sys
sys.path.insert(0, os.path.abspath('..'))

project = 'BSHT Bot'
copyright = '2026, BSHT Team'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
]

# docs/api.rst - 新建文件
API Documentation
=================

Audio Module
-------------

.. automodule:: audio_codec
   :members:
   :undoc-members:
   :show-inheritance:

Client Module
--------------

.. automodule:: bsht_client
   :members:
   :undoc-members:
   :show-inheritance:
```

### 8.2 README完善

**优化方案**:
```markdown
# README.md 增强

## BSHT Bot

> 业余无线电AI助手 - 支持语音识别、智能分析和微信推送

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://www.python.org/)
[![Code style](https://img.shields.io/badge/code%20style-black-4bar.svg)](https://github.com/psf/black)

### ✨ 特性

- 🎙️ **实时录音** - 高质量音频录制，支持多用户
- 🤖 **AI识别** - 语音识别 + 智能分析
- 📱 **微信推送** - 关键词匹配推送
- 🔊 **音频优化** - DSP预处理，提升识别率
- 💾 **数据存储** - SQLite数据库，可查询历史记录

### 🚀 快速开始

#### 安装

\`\`\`bash
git clone https://github.com/yourusername/bsht-bot.git
cd bsht-bot
pip install -r requirements.txt
\`\`\`

#### 配置

\`\`\`bash
cp .env.example .env
# 编辑 .env 填写配置
\`\`\`

#### 运行

\`\`\`bash
python bot_server.py
\`\`\`

### 📖 文档

- [部署指南](DEPLOY.md)
- [API文档](docs/api.md)
- [开发指南](docs/development.md)

### 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 📄 许可证

MIT License
```

---

## 🎯 优化优先级总结

### 🔥 高优先级 (立即执行)

1. **单元测试** - 提升代码质量和信心
2. **API密钥加密** - 提升安全性
3. **异步I/O** - 显著提升性能
4. **监控告警** - 提升可观测性

### ⚡ 中优先级 (1-2周内)

5. **缓存机制** - 减少重复计算
6. **模块化重构** - 提升可维护性
7. **类型注解** - 提升IDE支持
8. **Docker容器化** - 简化部署

### 📊 低优先级 (长期优化)

9. **API文档** - 提升开发体验
10. **性能监控** - 持续优化

---

## 📝 实施建议

### 第一步: 测试覆盖
```bash
# 安装pytest
pip install pytest pytest-cov pytest-asyncio

# 运行测试
pytest tests/ -v --cov=. --cov-report=html
```

### 第二步: 性能优化
```bash
# 实现异步版本
# 对比性能
python -m cProfile -s cumtime bot_server.py
```

### 第三步: 安全加固
```bash
# 加密API密钥
python utils/encrypt_secrets.py
```

---

**建议完成时间**: 2-4周
**预期收益**: 性能提升30-50%，代码质量提升，可维护性显著改善
