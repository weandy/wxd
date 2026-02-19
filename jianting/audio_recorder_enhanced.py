"""
增强的音频录音器 - 支持自动资源管理

主要改进:
1. 实现上下文管理器 (__enter__/__exit__)
2. 添加析构函数 (__del__) 作为安全网
3. 线程安全的资源清理
4. 全局实例跟踪，程序退出时自动清理
5. 改进的错误处理和日志记录
"""

import logging
import atexit
import threading
import weakref
from typing import Optional

logger = logging.getLogger(__name__)


class AudioRecorderEnhanced:
    """
    增强的音频录音器

    特性:
    - 支持上下文管理器 (with语句)
    - 自动资源清理
    - 线程安全
    - 幂等的cleanup方法

    Usage:
        # 方式1: 上下文管理器 (推荐)
        with AudioRecorderEnhanced() as recorder:
            data = recorder.read_frame()

        # 方式2: 手动清理
        recorder = AudioRecorderEnhanced()
        try:
            recorder.start_recording()
            data = recorder.read_frame()
        finally:
            recorder.cleanup()
    """

    # 类级别的实例跟踪
    _instances = weakref.WeakSet()
    _instances_lock = threading.Lock()

    def __init__(self, sample_rate=48000, frame_size=960, channels=1):
        """
        初始化录音器

        Args:
            sample_rate: 采样率 (Hz)
            frame_size: 帧大小 (采样数)
            channels: 声道数
        """
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.channels = channels

        self.pyaudio = None
        self.stream = None
        self.is_recording = False

        # 资源管理
        self._cleanup_called = False
        self._cleanup_lock = threading.Lock()

        # 注册到全局实例列表
        with self._instances_lock:
            self._instances.add(self)

        logger.debug(f"[AudioRecorderEnhanced] 创建实例: {sample_rate}Hz")

    def _init_pyaudio(self) -> bool:
        """初始化 PyAudio"""
        if self.pyaudio is not None:
            return True

        try:
            import pyaudio
            self.pyaudio = pyaudio.PyAudio()
            logger.debug("[AudioRecorderEnhanced] PyAudio 初始化成功")
            return True
        except ImportError as e:
            logger.error(f"[AudioRecorderEnhanced] PyAudio 未安装: {e}")
            return False
        except Exception as e:
            logger.error(f"[AudioRecorderEnhanced] PyAudio 初始化失败: {e}")
            return False

    def start_recording(self) -> bool:
        """
        开始录音

        Returns:
            是否成功启动
        """
        if self.is_recording:
            logger.debug("[AudioRecorderEnhanced] 已在录音状态")
            return True

        if not self._init_pyaudio():
            return False

        try:
            self.stream = self.pyaudio.open(
                format=self.pyaudio.get_format_from_width(2),  # 16-bit
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.frame_size
            )

            self.is_recording = True
            logger.info(f"[AudioRecorderEnhanced] 开始录音: {self.sample_rate}Hz")
            return True

        except Exception as e:
            logger.error(f"[AudioRecorderEnhanced] 启动录音失败: {e}")
            self.cleanup()
            return False

    def read_frame(self, timeout_ms=1000):
        """
        读取一帧音频数据 (阻塞)

        Args:
            timeout_ms: 超时时间(毫秒)

        Returns:
            numpy array or None: PCM音频数据
        """
        if not self.is_recording or not self.stream:
            logger.warning("[AudioRecorderEnhanced] 未在录音状态")
            return None

        try:
            import numpy as np

            # 读取音频数据
            data = self.stream.read(self.frame_size, exception_on_overflow=False)

            # 转换为 numpy 数组
            pcm_data = np.frombuffer(data, dtype=np.int16)

            return pcm_data

        except Exception as e:
            logger.error(f"[AudioRecorderEnhanced] 读取音频失败: {e}")
            # 发生错误时自动清理
            self.cleanup()
            return None

    def stop_recording(self):
        """
        停止录音 (不释放资源)

        注意: 这只是停止数据采集，不会释放PyAudio资源
              如果要完全释放资源，请调用 cleanup()
        """
        if not self.is_recording:
            return

        self.is_recording = False

        if self.stream:
            try:
                self.stream.stop_stream()
                logger.debug("[AudioRecorderEnhanced] 录音流已停止")
            except Exception as e:
                logger.error(f"[AudioRecorderEnhanced] 停止流失败: {e}")

    def cleanup(self):
        """
        清理资源 (线程安全，幂等)

        可以多次调用，不会重复清理。
        这是释放所有资源的方法，应该在使用完录音器后调用。
        """
        with self._cleanup_lock:
            if self._cleanup_called:
                return

            self._cleanup_called = True
            logger.debug("[AudioRecorderEnhanced] 开始清理资源")

            # 停止录音
            self.stop_recording()

            # 关闭流
            if self.stream:
                try:
                    self.stream.close()
                    logger.debug("[AudioRecorderEnhanced] 音频流已关闭")
                except Exception as e:
                    logger.error(f"[AudioRecorderEnhanced] 关闭流失败: {e}")
                finally:
                    self.stream = None

            # 终止 PyAudio
            if self.pyaudio:
                try:
                    self.pyaudio.terminate()
                    logger.debug("[AudioRecorderEnhanced] PyAudio 已终止")
                except Exception as e:
                    logger.error(f"[AudioRecorderEnhanced] 终止PyAudio失败: {e}")
                finally:
                    self.pyaudio = None

            logger.info("[AudioRecorderEnhanced] 资源清理完成")

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
            logger.warning("[AudioRecorderEnhanced] 实例被销毁但未调用cleanup()，自动清理")
            self.cleanup()

    @classmethod
    def cleanup_all_instances(cls):
        """清理所有实例的资源 (程序退出时调用)"""
        with cls._instances_lock:
            instances = list(cls._instances)

        if instances:
            logger.info(f"[AudioRecorderEnhanced] 清理 {len(instances)} 个实例")
            for instance in instances:
                instance.cleanup()

    @classmethod
    def get_instance_count(cls) -> int:
        """获取当前实例数量"""
        with cls._instances_lock:
            return len(list(cls._instances))


# 注册程序退出时的清理函数
atexit.register(AudioRecorderEnhanced.cleanup_all_instances)


# 为了向后兼容，创建别名
AudioRecorder = AudioRecorderEnhanced
