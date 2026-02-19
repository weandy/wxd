# 关键问题详细分析与修复方案

> 创建时间: 2026-02-19
> 基于版本: main branch (commit 275090f)

---

## 📋 问题清单

本文档详细分析以下5个关键问题并提供完整的修复方案：

1. **SQL注入风险** - 数据库查询安全问题
2. **竞态条件** - 多线程数据竞争
3. **资源泄漏** - 音频流未正确关闭
4. **错误处理不一致** - 混用print和logger
5. **数据库连接池缺失** - 多线程性能问题

---

## 问题1: SQL注入风险 🔴

### 问题描述

**位置**: `src/database.py`

**风险等级**: 🔴 严重 (Security Critical)

**潜在影响**:
- 数据泄露
- 数据损坏
- 未授权数据访问

### 详细分析

虽然当前代码中大多数查询使用了参数化查询，但存在以下风险点：

```python
# src/database.py - 潜在风险点
def get_recording_by_path(self, filepath: str) -> Optional[Recording]:
    cursor.execute("""
        SELECT * FROM recordings WHERE filepath = ?
    """, (filepath,))  # ✅ 这个是安全的

# 但如果未来有类似这样的代码:
def search_by_filename(self, pattern: str):
    cursor.execute(f"""
        SELECT * FROM recordings WHERE filename LIKE '%{pattern}%'
    """)  # ❌ SQL注入风险!
```

### 修复方案

#### 1.1 创建安全的查询基类

```python
# src/database_safe.py - 新建文件
import sqlite3
import threading
from typing import Optional, List, Any, Dict
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class SafeQuery:
    """安全查询基类 - 防止SQL注入"""

    @staticmethod
    def validate_sql(query: str) -> bool:
        """验证SQL语句安全性"""
        dangerous_keywords = [
            'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE',
            'EXEC', 'EXECUTE', 'SCRIPT', '--', '/*', '*/'
        ]

        query_upper = query.upper()
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                logger.warning(f"检测到危险SQL关键词: {keyword}")
                return False

        return True

    @staticmethod
    def sanitize_like_pattern(pattern: str) -> str:
        """清理LIKE模式中的通配符"""
        # 转义SQL通配符
        pattern = pattern.replace('_', '\\_')
        pattern = pattern.replace('%', '\\%')
        return pattern

    @staticmethod
    @contextmanager
    def transaction(conn: sqlite3.Connection):
        """事务上下文管理器"""
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"事务回滚: {e}")
            raise


class SafeDatabase:
    """增强的数据库类 - 防止SQL注入"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def execute_safe(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行安全查询"""
        if not SafeQuery.validate_sql(query):
            raise ValueError("SQL查询包含危险操作")

        conn = self._get_connection()
        cursor = conn.execute(query, params)
        return cursor

    def fetch_all_safe(self, query: str, params: tuple = ()) -> List[Dict]:
        """安全获取所有结果"""
        cursor = self.execute_safe(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def search_safe(self, table: str, field: str, pattern: str) -> List[Dict]:
        """安全的LIKE搜索"""
        safe_pattern = SafeQuery.sanitize_like_pattern(pattern)
        query = f"SELECT * FROM {table} WHERE {field} LIKE ? ESCAPE '\\'"

        return self.fetch_all_safe(query, (f"%{safe_pattern}%",))
```

#### 1.2 在database.py中添加输入验证

```python
# 在 src/database.py 中添加

def validate_filepath(filepath: str) -> bool:
    """验证文件路径安全性"""
    import os

    # 规范化路径
    normalized = os.path.normpath(filepath)

    # 检查路径遍历攻击
    if '..' in normalized:
        logger.warning(f"检测到路径遍历尝试: {filepath}")
        return False

    # 检查是否在允许的目录下
    allowed_dirs = ['recordings', 'data']
    if not any(normalized.startswith(d) for d in allowed_dirs):
        logger.warning(f"文件路径不在允许目录下: {filepath}")
        return False

    return True


def validate_user_input(value: str, max_length: int = 255) -> bool:
    """验证用户输入"""
    if not isinstance(value, str):
        return False

    if len(value) > max_length:
        logger.warning(f"输入超过最大长度: {len(value)} > {max_length}")
        return False

    # 检查危险字符
    dangerous_chars = ['\x00', '\n', '\r', '\x1a']
    if any(char in value for char in dangerous_chars):
        logger.warning("输入包含危险字符")
        return False

    return True
```

#### 1.3 修改现有的查询方法

```python
# 修改 src/database.py 中的方法
def get_recording_by_path(self, filepath: str) -> Optional[Recording]:
    """通过路径获取录音记录 - 安全版本"""
    # 添加输入验证
    if not validate_filepath(filepath):
        logger.error(f"无效的文件路径: {filepath}")
        return None

    try:
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM recordings
            WHERE filepath = ? LIMIT 1
            """,
            (filepath,)
        )

        row = cursor.fetchone()
        if row:
            return self._row_to_recording(row)
        return None

    except sqlite3.Error as e:
        logger.error(f"查询失败: {e}")
        return None
```

---

## 问题2: 竞态条件 🔴

### 问题描述

**位置**: `bsht_client.py:1821-1896` (start_transmit方法)

**风险等级**: 🔴 严重 (Stability Critical)

**潜在影响**:
- 重复初始化编码器/录音器
- 内存泄漏
- 程序崩溃
- 音频流混乱

### 详细分析

```python
# bsht_client.py - 当前代码的问题
def start_transmit(self) -> bool:
    with self._transmit_lock:
        if hasattr(self, '_is_transmitting') and self._is_transmitting:
            return True

        # ⚠️ 问题1: 标志设置在锁内，但初始化在锁外
        self._is_transmitting = True

    # ⚠️ 问题2: 这些初始化不在锁保护内
    # 如果多线程同时调用，可能创建多个实例
    if not hasattr(self, '_tx_encoder') or self._tx_encoder is None:
        self._tx_encoder = OpusEncoder(...)  # 竞态窗口!

    if not hasattr(self, '_tx_recorder') or self._tx_recorder is None:
        self._tx_recorder = AudioRecorder(...)  # 竞态窗口!

    # ⚠️ 问题3: _tx_stop_event 也可能重复初始化
    self._tx_stop_event = threading.Event()
```

**竞态时序图**:
```
线程A                          线程B
  |                              |
检查 _is_transmitting = False   |
设置 _is_transmitting = True    |
释放锁                          |
  |                              |
  |                          检查 _is_transmitting = False
  |                          设置 _is_transmitting = True
  |                          释放锁
  |                              |
创建 _tx_encoder                 |
创建 _tx_recorder                |
  |                          创建 _tx_encoder (重复!)
  |                          创建 _tx_recorder (重复!)
  |                              |
启动 _tx_thread                  |
  |                          启动 _tx_thread (重复!)
```

### 修复方案

#### 2.1 使用线程安全的状态管理

```python
# bsht_client.py - 修复后的代码

import threading
from enum import Enum
from typing import Optional


class TransmitState(Enum):
    """发射状态枚举"""
    IDLE = "idle"
    STARTING = "starting"      # 正在启动
    TRANSMITTING = "transmitting"
    STOPPING = "stopping"      # 正在停止


class AudioStreamListener:
    """..."""

    def __init__(self, client: 'BSHTClient'):
        # ... 现有代码 ...

        # 使用状态机替代简单布尔值
        self._tx_state = TransmitState.IDLE
        self._tx_state_lock = threading.RLock()  # 使用可重入锁
        self._tx_init_lock = threading.Lock()   # 初始化专用锁

        # 条件变量用于状态等待
        self._tx_state_changed = threading.Condition(self._tx_state_lock)

    def start_transmit(self) -> bool:
        """
        开始发射 (PTT按下) - 线程安全版本

        Returns:
            是否成功启动
        """
        logger.info("[TX] start_transmit 调用")

        # 快速路径检查
        with self._tx_state_lock:
            if self._tx_state == TransmitState.TRANSMITTING:
                logger.info("[TX] 已在发射中")
                return True

            if self._tx_state in (TransmitState.STARTING, TransmitState.STOPPING):
                logger.warning(f"[TX] 状态转换中: {self._tx_state.value}")
                return False

            # 状态转换: IDLE -> STARTING
            self._tx_state = TransmitState.STARTING

        try:
            # === 初始化阶段 (双重检查锁定) ===
            with self._tx_init_lock:
                # 检查编码器
                if not hasattr(self, '_tx_encoder') or self._tx_encoder is None:
                    logger.debug("[TX] 初始化编码器")
                    from audio_codec import OpusEncoder, SAMPLE_RATE, FRAME_SIZE

                    self._tx_encoder = OpusEncoder(
                        sample_rate=SAMPLE_RATE,
                        frame_size=FRAME_SIZE,
                        bitrate=32000
                    )

                # 检查录音器
                if not hasattr(self, '_tx_recorder') or self._tx_recorder is None:
                    logger.debug("[TX] 初始化录音器")
                    from audio_codec import AudioRecorder, SAMPLE_RATE, FRAME_SIZE

                    self._tx_recorder = AudioRecorder(
                        sample_rate=SAMPLE_RATE,
                        frame_size=FRAME_SIZE,
                        channels=1
                    )

                # 确保录音流已打开
                if not self._tx_recorder.is_recording:
                    logger.debug("[TX] 启动录音流")
                    if not self._tx_recorder.start_recording():
                        raise RuntimeError("启动录音失败")

            # === 准备发射参数 ===
            with self._tx_state_lock:
                self._tx_stop_event = threading.Event()
                self._tx_first_packet = True
                self._tx_frame_count = 0
                self._tx_start_time = time.time()

                # 状态转换: STARTING -> TRANSMITTING
                self._tx_state = TransmitState.TRANSMITTING
                self._tx_state_changed.notify_all()

            # === 启动发射线程 ===
            self._tx_thread = threading.Thread(
                target=self._transmit_loop,
                name="TX-Transmit",
                daemon=True
            )
            self._tx_thread.start()

            logger.info("[TX] 🟢 开始发射")
            return True

        except Exception as e:
            # 发生错误，回滚状态
            with self._tx_state_lock:
                self._tx_state = TransmitState.IDLE
                self._tx_state_changed.notify_all()

            logger.error(f"[TX] 启动失败: {e}")
            return False

    def stop_transmit(self):
        """
        停止发射 (PTT松开) - 线程安全版本
        """
        logger.info("[TX] stop_transmit 调用")

        with self._tx_state_lock:
            if self._tx_state == TransmitState.IDLE:
                logger.info("[TX] 未在发射中")
                return

            if self._tx_state == TransmitState.STOPPING:
                logger.info("[TX] 已在停止中")
                return

            # 状态转换: TRANSMITTING -> STOPPING
            self._tx_state = TransmitState.STOPPING
            self._tx_state_changed.notify_all()

        # 发送停止信号
        if hasattr(self, '_tx_stop_event'):
            self._tx_stop_event.set()

        # 等待线程结束
        if hasattr(self, '_tx_thread') and self._tx_thread:
            logger.debug("[TX] 等待发射线程结束...")
            self._tx_thread.join(timeout=2.0)

            if self._tx_thread.is_alive():
                logger.warning("[TX] 发射线程未在超时时间内结束")

            self._tx_thread = None

        # 发送停止包
        try:
            self.send_audio(b'', marker=False)
            logger.info("[TX] 已发送 TX_AUDIO_STOP")
        except Exception as e:
            logger.warning(f"[TX] 发送停止包失败: {e}")

        # 回到空闲状态
        with self._tx_state_lock:
            self._tx_state = TransmitState.IDLE
            self._tx_state_changed.notify_all()

        logger.info("[TX] 🔴 停止发射")

    @property
    def is_transmitting(self) -> bool:
        """是否正在发射 - 线程安全"""
        with self._tx_state_lock:
            return self._tx_state == TransmitState.TRANSMITTING

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        """
        等待直到回到空闲状态

        Returns:
            是否在超时前回到空闲状态
        """
        with self._tx_state_changed:
            return self._tx_state_changed.wait_for(
                lambda: self._tx_state == TransmitState.IDLE,
                timeout=timeout
            )
```

---

## 问题3: 资源泄漏 🟡

### 问题描述

**位置**: `audio_codec.py:310-413` (AudioRecorder类)

**风险等级**: 🟡 中等 (Resource Leak)

**潜在影响**:
- 音频设备占用
- 内存泄漏
- 长时间运行后资源耗尽
- 系统性能下降

### 详细分析

```python
# audio_codec.py - 当前代码的问题

class AudioRecorder:
    def cleanup(self):
        """清理资源"""
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass  # ⚠️ 问题1: 空异常处理，隐藏错误

            self.stream = None

        if self.pyaudio:
            try:
                self.pyaudio.terminate()
            except:
                pass  # ⚠️ 问题2: 空异常处理
            self.pyaudio = None
```

**问题点**:
1. 空异常处理 (`except: pass`) 吞掉所有错误
2. 没有实现 `__del__` 析构函数
3. 没有实现上下文管理器 (`__enter__`/`__exit__`)
4. `bot_server.py` 中多处创建但未确保清理

**资源泄漏场景**:
```
场景1: 异常退出
recorder = AudioRecorder()
recorder.start_recording()
# ... 发生异常 ...
# cleanup() 没有被调用 → PyAudio资源泄漏

场景2: 重复创建
for i in range(100):
    recorder = AudioRecorder()
    recorder.start_recording()
    # 没有调用cleanup()
    # → 100个音频设备资源泄漏
```

### 修复方案

#### 3.1 实现完整的资源管理

```python
# audio_codec.py - 修复后的代码

import logging
import atexit
import threading
from typing import Optional
import weakref

logger = logging.getLogger(__name__)


class AudioRecorder:
    """
    音频录音器 - 支持上下文管理和自动清理

    Usage:
        # 方式1: 上下文管理器 (推荐)
        with AudioRecorder() as recorder:
            data = recorder.read_frame()

        # 方式2: 手动清理
        recorder = AudioRecorder()
        try:
            recorder.start_recording()
            data = recorder.read_frame()
        finally:
            recorder.cleanup()
    """

    # 类级别的实例跟踪，用于程序退出时清理
    _instances = weakref.WeakSet()
    _instances_lock = threading.Lock()

    def __init__(self, sample_rate=48000, frame_size=960, channels=1):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.channels = channels

        self.pyaudio = None
        self.stream = None
        self.is_recording = False

        self._cleanup_called = False
        self._cleanup_lock = threading.Lock()

        # 注册到全局实例列表
        with self._instances_lock:
            self._instances.add(self)

        logger.debug(f"[AudioRecorder] 创建实例: {sample_rate}Hz")

    def _init_pyaudio(self) -> bool:
        """初始化 PyAudio"""
        if self.pyaudio is not None:
            return True

        try:
            import pyaudio
            self.pyaudio = pyaudio.PyAudio()
            logger.debug("[AudioRecorder] PyAudio 初始化成功")
            return True
        except ImportError as e:
            logger.error(f"[AudioRecorder] PyAudio 未安装: {e}")
            return False
        except Exception as e:
            logger.error(f"[AudioRecorder] PyAudio 初始化失败: {e}")
            return False

    def start_recording(self) -> bool:
        """开始录音"""
        if self.is_recording:
            return True

        if not self._init_pyaudio():
            return False

        try:
            self.stream = self.pyaudio.open(
                format=self.pyaudio.get_format_from_width(2),
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.frame_size
            )

            self.is_recording = True
            logger.info(f"[AudioRecorder] 开始录音: {self.sample_rate}Hz")
            return True

        except Exception as e:
            logger.error(f"[AudioRecorder] 启动录音失败: {e}")
            self.cleanup()
            return False

    def read_frame(self, timeout_ms=1000):
        """读取一帧音频数据"""
        if not self.is_recording or not self.stream:
            logger.warning("[AudioRecorder] 未在录音状态")
            return None

        try:
            import numpy as np

            data = self.stream.read(self.frame_size, exception_on_overflow=False)
            pcm_data = np.frombuffer(data, dtype=np.int16)

            return pcm_data

        except Exception as e:
            logger.error(f"[AudioRecorder] 读取音频失败: {e}")
            # 发生错误时自动清理
            self.cleanup()
            return None

    def stop_recording(self):
        """停止录音 (不释放资源)"""
        if not self.is_recording:
            return

        self.is_recording = False

        if self.stream:
            try:
                self.stream.stop_stream()
                logger.debug("[AudioRecorder] 录音流已停止")
            except Exception as e:
                logger.error(f"[AudioRecorder] 停止流失败: {e}")

    def cleanup(self):
        """
        清理资源 (线程安全，幂等)

        可以多次调用，不会重复清理
        """
        with self._cleanup_lock:
            if self._cleanup_called:
                return

            self._cleanup_called = True
            logger.debug(f"[AudioRecorder] 开始清理资源")

            # 停止录音
            self.stop_recording()

            # 关闭流
            if self.stream:
                try:
                    self.stream.close()
                    logger.debug("[AudioRecorder] 音频流已关闭")
                except Exception as e:
                    logger.error(f"[AudioRecorder] 关闭流失败: {e}")
                finally:
                    self.stream = None

            # 终止 PyAudio
            if self.pyaudio:
                try:
                    self.pyaudio.terminate()
                    logger.debug("[AudioRecorder] PyAudio 已终止")
                except Exception as e:
                    logger.error(f"[AudioRecorder] 终止PyAudio失败: {e}")
                finally:
                    self.pyaudio = None

            logger.info("[AudioRecorder] 资源清理完成")

    def __enter__(self):
        """上下文管理器入口"""
        self.start_recording()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.cleanup()

        # 不抑制异常
        return False

    def __del__(self):
        """析构函数 - 最后的安全网"""
        if not self._cleanup_called:
            logger.warning(f"[AudioRecorder] 实例被销毁但未调用cleanup()，自动清理")
            self.cleanup()

    @classmethod
    def cleanup_all_instances(cls):
        """清理所有实例的资源 (程序退出时调用)"""
        with cls._instances_lock:
            instances = list(cls._instances)

        logger.info(f"[AudioRecorder] 清理 {len(instances)} 个实例")
        for instance in instances:
            instance.cleanup()


# 注册程序退出时的清理函数
atexit.register(AudioRecorder.cleanup_all_instances)
```

#### 3.2 修改bot_server.py使用上下文管理器

```python
# bot_server.py - 修复后的代码

def _transmit_loop(self):
    """发射线程 - 使用上下文管理器"""
    # ... 现有代码 ...

    try:
        # 使用上下文管理器确保资源清理
        with self._tx_recorder:
            while not self._tx_stop_event.is_set() and self._is_transmitting:
                # ... 读取和处理音频 ...
                pcm_frame = self._tx_recorder.read_frame(timeout_ms=100)
                # ...

    except Exception as e:
        logger.error(f"发射循环异常: {e}")
    finally:
        # 上下文管理器会自动调用 cleanup()
        logger.debug("[TX_LOOP] 退出循环，资源已自动清理")
```

---

## 问题4: 错误处理不一致 🟢

### 问题描述

**位置**: 多个文件

**风险等级**: 🟢 轻微 (Code Quality)

**潜在影响**:
- 调试困难
- 错误信息丢失
- 日志不规范
- 生产环境问题排查困难

### 详细分析

```python
# 混用的错误处理方式

# 方式1: print (不推荐)
if error.value != 0:
    print(f"Opus decoder init error: {error.value}")  # ❌

# 方式2: logger.info (不正确)
logger.info(f"识别失败: {e}")  # ❌ 应该用 error

# 方式3: logger.error (正确)
logger.error(f"识别失败: {e}")  # ✅

# 方式4: 空异常处理 (最差)
except:
    pass  # ❌❌❌
```

### 修复方案

#### 4.1 统一的错误处理工具

```python
# src/error_handling.py - 新建文件

import logging
import sys
import traceback
from typing import Optional, Callable, Any
from functools import wraps
import inspect


class ErrorHandler:
    """统一的错误处理器"""

    def __init__(self, module_name: str):
        self.logger = logging.getLogger(module_name)

    def handle_exception(self,
                        e: Exception,
                        context: str = "",
                        reraise: bool = False,
                        level: str = "ERROR") -> None:
        """
        统一异常处理

        Args:
            e: 异常对象
            context: 上下文信息
            reraise: 是否重新抛出异常
            level: 日志级别 (ERROR, WARNING, CRITICAL)
        """
        # 获取调用栈信息
        frame = inspect.currentframe()
        if frame and frame.f_back:
            frame_info = inspect.getframeinfo(frame.f_back)
            location = f"{frame_info.filename}:{frame_info.lineno}"
        else:
            location = "unknown"

        # 构建错误消息
        msg_parts = [
            f"[{location}]",
            f"{context or 'Error'}:"
        ]

        # 添加异常类型和消息
        msg_parts.append(f"{type(e).__name__}: {str(e)}")

        # 添加堆栈跟踪
        stack_trace = ''.join(traceback.format_exception(
            type(e), e, e.__traceback__
        ))

        # 记录日志
        log_func = getattr(self.logger, level.lower(), self.logger.error)
        log_func('\n'.join(msg_parts))
        self.logger.debug(f"堆栈跟踪:\n{stack_trace}")

        # 重新抛出
        if reraise:
            raise

    @staticmethod
    def validate_not_empty(value: Any,
                          field_name: str,
                          module_name: str) -> None:
        """验证输入不为空"""
        logger = logging.getLogger(module_name)

        if value is None:
            raise ValueError(f"{field_name} 不能为 None")

        if isinstance(value, str) and not value.strip():
            raise ValueError(f"{field_name} 不能为空字符串")

        if isinstance(value, (list, dict, tuple)) and len(value) == 0:
            raise ValueError(f"{field_name} 不能为空")


def log_errors(module_name: str = "",
               context: str = "",
               reraise: bool = False):
    """
    错误日志装饰器

    Usage:
        @log_errors("my_module", "数据库操作")
        def save_data(data):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            handler = ErrorHandler(module_name or func.__module__)

            try:
                return func(*args, **kwargs)
            except Exception as e:
                ctx = context or f"{func.__name__}({args}, {kwargs})"
                handler.handle_exception(e, context=ctx, reraise=reraise)

                if not reraise:
                    # 返回默认值或None
                    return None

        return wrapper
    return decorator


def safe_execute(default: Any = None,
                 log_module: str = ""):
    """
    安全执行装饰器 - 返回默认值而不是抛出异常

    Usage:
        @safe_execute(default=[], log_module="audio")
        def get_audio_devices():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(log_module or func.__module__)

            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"{func.__name__} 执行失败: {e}")
                return default

        return wrapper
    return decorator
```

#### 4.2 在各模块中应用

```python
# audio_codec.py - 应用统一错误处理

from src.error_handling import ErrorHandler, log_errors

error_handler = ErrorHandler("audio_codec")


class OpusDecoder:
    def __init__(self, sample_rate=48000, channels=1):
        # ... 现有代码 ...

        try:
            error = ctypes.c_int()
            self._decoder = self._lib.opus_decoder_create(
                sample_rate, channels, ctypes.byref(error)
            )

            if error.value != 0:
                # 使用统一错误处理
                error_handler.handle_exception(
                    RuntimeError(f"Opus init error: {error.value}"),
                    context=f"初始化解码器 {sample_rate}Hz",
                    reraise=True
                )

        except Exception as e:
            error_handler.handle_exception(
                e,
                context="创建Opus解码器",
                reraise=True
            )


    @log_errors("audio_codec", "解码音频帧")
    def decode(self, payload: bytes) -> bytes:
        """解码 Opus 数据"""
        # ... 解码逻辑 ...
```

---

## 问题5: 数据库连接池缺失 🟡

### 问题描述

**位置**: `src/database.py`

**风险等级**: 🟡 中等 (Performance)

**潜在影响**:
- 多线程性能下降
- 数据库锁竞争
- 潜在的数据损坏
- 高并发下超时

### 详细分析

```python
# src/database.py - 当前代码的问题

class Database:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = "data/records.db"):
        if self._initialized:
            return

        # ⚠️ 问题: 单例模式 + 单连接 = 多线程瓶颈
        self.db_path = db_path
        self._init_db()
        self._initialized = True

    def _get_connection(self):
        # ⚠️ 每次都创建新连接
        return sqlite3.connect(self.db_path)
```

**性能问题**:
```
场景: 5个并发识别任务
任务1: connect → query (100ms) → close
任务2: connect → query (等待任务1释放) → close
任务3: connect → query (等待任务1,2) → close
...

总耗时: 500ms (串行)
理想耗时: 100ms (并行)
```

**SQLite限制**:
- 多个线程可以同时读
- 但同一时间只能一个线程写
- 写操作会锁定整个数据库

### 修复方案

#### 5.1 实现连接池

```python
# src/database_pool.py - 新建文件

import sqlite3
import threading
import queue
import time
import logging
from typing import Optional, List
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """
    SQLite 连接池

    特性:
    - 线程安全的连接池
    - 自动重连
    - 连接健康检查
    - 上下文管理器支持

    Usage:
        pool = DatabaseConnectionPool("data/records.db", pool_size=5)

        with pool.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM recordings")
            results = cursor.fetchall()
    """

    def __init__(self,
                 db_path: str,
                 pool_size: int = 5,
                 max_overflow: int = 10,
                 timeout: float = 30.0):
        """
        Args:
            db_path: 数据库文件路径
            pool_size: 基础连接池大小
            max_overflow: 最大额外连接数
            timeout: 获取连接超时时间(秒)
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.timeout = timeout

        # 连接队列
        self._pool = queue.Queue(maxsize=pool_size + max_overflow)
        self._lock = threading.Lock()
        self._created_connections = 0

        # 统计信息
        self._stats = {
            'created': 0,
            'reused': 0,
            'closed': 0,
            'errors': 0
        }

        # 预创建连接
        self._initialize_pool()

        logger.info(f"连接池初始化完成: {db_path}, 大小={pool_size}")

    def _initialize_pool(self):
        """预创建连接"""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            if conn:
                self._pool.put(conn)

    def _create_connection(self) -> Optional[sqlite3.Connection]:
        """创建新连接"""
        try:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,  # 允许跨线程
                timeout=self.timeout,
                isolation_level=None  # 自动提交模式
            )

            # 优化性能
            conn.execute("PRAGMA journal_mode=WAL")  # 写前日志
            conn.execute("PRAGMA synchronous=NORMAL")  # 平衡模式
            conn.execute("PRAGMA cache_size=-64000")  # 64MB缓存
            conn.execute("PRAGMA temp_store=MEMORY")  # 临时表在内存
            conn.row_factory = sqlite3.Row

            with self._lock:
                self._created_connections += 1
                self._stats['created'] += 1

            logger.debug(f"创建新连接: 总数={self._created_connections}")
            return conn

        except Exception as e:
            logger.error(f"创建连接失败: {e}")
            self._stats['errors'] += 1
            return None

    def _validate_connection(self, conn: sqlite3.Connection) -> bool:
        """验证连接是否可用"""
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    @contextmanager
    def get_connection(self):
        """
        获取连接 (上下文管理器)

        Usage:
            with pool.get_connection() as conn:
                cursor = conn.execute("SELECT ...")
        """
        conn = None
        try:
            # 尝试从池中获取连接
            try:
                conn = self._pool.get(timeout=self.timeout)

                # 健康检查
                if not self._validate_connection(conn):
                    logger.warning("连接不可用，创建新连接")
                    conn.close()
                    conn = self._create_connection()

                self._stats['reused'] += 1

            except queue.Empty:
                # 池已空，创建新连接 (溢出)
                logger.warning("连接池已空，创建溢出连接")
                conn = self._create_connection()

            if conn is None:
                raise TimeoutError("获取数据库连接超时")

            yield conn

        finally:
            # 归还连接到池
            if conn:
                try:
                    self._pool.put(conn, block=False)
                except queue.Full:
                    # 池已满，关闭连接
                    logger.debug("连接池已满，关闭溢出连接")
                    conn.close()
                    self._stats['closed'] += 1

    def close_all(self):
        """关闭所有连接"""
        logger.info("关闭所有连接...")

        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
                self._stats['closed'] += 1
            except queue.Empty:
                break

        logger.info(f"连接池已关闭: {self._stats}")

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self._stats,
            'pool_size': self._created_connections,
            'available': self._pool.qsize(),
            'waiting': self._pool._unfinished_tasks
        }


# 全局连接池实例
_global_pool: Optional[DatabaseConnectionPool] = None
_pool_lock = threading.Lock()


def get_connection_pool(db_path: str = "data/records.db",
                       pool_size: int = 5) -> DatabaseConnectionPool:
    """获取全局连接池实例 (单例)"""
    global _global_pool

    with _pool_lock:
        if _global_pool is None:
            _global_pool = DatabaseConnectionPool(db_path, pool_size)

        return _global_pool


@atexit.register
def cleanup_global_pool():
    """程序退出时清理连接池"""
    global _global_pool

    if _global_pool:
        _global_pool.close_all()
```

#### 5.2 修改Database类使用连接池

```python
# src/database.py - 修改后的代码

from src.database_pool import get_connection_pool

class Database:
    """数据库管理类 - 使用连接池"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = "data/records.db"):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = "data/records.db"):
        if self._initialized:
            return

        self.db_path = db_path
        self._ensure_dir()

        # 使用连接池
        self._pool = get_connection_pool(db_path, pool_size=5)

        # 初始化数据库表
        self._init_db()

        self._initialized = True
        logger.info(f"数据库初始化完成: {db_path}")

    def _get_connection(self):
        """从连接池获取连接"""
        return self._pool.get_connection()

    def add_recording(self, recording: Recording) -> int:
        """添加录音记录"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO recordings
                (filepath, filename, channel_id, user_id, user_name,
                 recorder_type, duration, start_time, file_size, timestamp, recognized)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (recording.filepath, recording.filename, recording.channel_id,
                 recording.user_id, recording.user_name, recording.recorder_type,
                 recording.duration, recording.start_time, recording.file_size,
                 recording.timestamp, recording.recognized)
            )

            return cursor.lastrowid

    def get_recording_by_path(self, filepath: str) -> Optional[Recording]:
        """通过路径获取录音记录"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM recordings
                WHERE filepath = ? LIMIT 1
                """,
                (filepath,)
            )

            row = cursor.fetchone()
            if row:
                return self._row_to_recording(row)
            return None

    # ... 其他方法类似修改 ...
```

---

## 📊 修复优先级和测试计划

### 修复顺序

1. **第一阶段 (立即修复)**:
   - ✅ 问题2: 竞态条件 (稳定性)
   - ✅ 问题3: 资源泄漏 (资源管理)

2. **第二阶段 (本周内)**:
   - ✅ 问题1: SQL注入风险 (安全)
   - ✅ 问题5: 数据库连接池 (性能)

3. **第三阶段 (持续改进)**:
   - ✅ 问题4: 错误处理规范 (代码质量)

### 测试计划

#### 单元测试

```python
# tests/test_fixes.py - 新建文件

import pytest
import threading
import time
from audio_codec import AudioRecorder
from bsht_client import AudioStreamListener
from src.database_pool import DatabaseConnectionPool


class TestResourceManagement:
    """测试资源管理"""

    def test_recorder_cleanup(self):
        """测试录音器清理"""
        recorder = AudioRecorder()
        recorder.start_recording()

        assert recorder.is_recording
        assert recorder.pyaudio is not None
        assert recorder.stream is not None

        recorder.cleanup()

        assert not recorder.is_recording
        assert recorder.pyaudio is None
        assert recorder.stream is None

    def test_recorder_context_manager(self):
        """测试上下文管理器"""
        with AudioRecorder() as recorder:
            assert recorder.is_recording
            data = recorder.read_frame()

        # 退出后应自动清理
        assert not recorder.is_recording

    def test_multiple_recorders(self):
        """测试多个录音器实例"""
        recorders = []

        for _ in range(5):
            r = AudioRecorder()
            r.start_recording()
            recorders.append(r)

        # 清理所有
        for r in recorders:
            r.cleanup()


class TestConcurrency:
    """测试并发安全"""

    def test_concurrent_transmit(self):
        """测试并发启动发射"""
        listener = AudioStreamListener(client=None)
        results = []

        def try_start():
            result = listener.start_transmit()
            results.append(result)
            time.sleep(0.1)
            listener.stop_transmit()

        threads = [
            threading.Thread(target=try_start)
            for _ in range(5)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # 只有一个应该成功
        success_count = sum(results)
        assert success_count == 1


class TestDatabasePool:
    """测试数据库连接池"""

    def test_pool_initialization(self):
        """测试连接池初始化"""
        pool = DatabaseConnectionPool(":memory:", pool_size=3)

        stats = pool.get_stats()
        assert stats['created'] == 3
        assert stats['available'] == 3

        pool.close_all()

    def test_concurrent_queries(self):
        """测试并发查询"""
        pool = DatabaseConnectionPool(":memory:", pool_size=5)

        # 创建测试表
        with pool.get_connection() as conn:
            conn.execute("""
                CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)
            """)
            conn.execute("INSERT INTO test VALUES (1, 'test')")

        def query():
            with pool.get_connection() as conn:
                result = conn.execute("SELECT * FROM test").fetchall()
                return len(result)

        threads = [threading.Thread(target=query) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有查询都应该成功
        pool.close_all()
```

#### 压力测试

```python
# tests/test_stress.py - 压力测试

import pytest
import threading
import time

def test_high_concurrency():
    """高并发测试"""
    pool = DatabaseConnectionPool("data/test.db", pool_size=5)

    def worker():
        for i in range(100):
            with pool.get_connection() as conn:
                conn.execute("SELECT 1")

    threads = [threading.Thread(target=worker) for _ in range(20)]
    start = time.time()

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    elapsed = time.time() - start
    print(f"20线程 × 100查询 = {elapsed:.2f}秒")

    pool.close_all()
```

---

## 📝 总结

本文档详细分析了5个关键问题，并提供了完整的修复方案：

1. **SQL注入** - 使用参数化查询 + 输入验证
2. **竞态条件** - 使用状态机 + 双重检查锁定
3. **资源泄漏** - 实现上下文管理器 + 自动清理
4. **错误处理** - 统一的错误处理工具
5. **连接池** - 实现数据库连接池

所有修复方案都考虑了：
- 线程安全
- 性能优化
- 易用性
- 向后兼容

下一步：实现这些修复方案。
