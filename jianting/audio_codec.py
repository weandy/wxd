"""
音频编解码模块

包含 Opus 编解码器、音频采集器、播放器和 PTT 控制器

参考文档:
- HT应用典型通话流程详细分析.md
- Python脚本完成度分析报告.md
"""

import ctypes
import os
import sys
import numpy as np
import threading
import time
import logging
from typing import Optional, Callable
from enum import Enum

# 创建模块 logger
logger = logging.getLogger("AudioCodec")

# 异步优化模块 - 用于CPU密集型任务的线程池处理
try:
    from async_optimization import get_thread_pool, run_in_pool
except ImportError:
    # 如果异步优化模块不存在，提供空实现
    def run_in_pool(pool_type="cpu"):
        def decorator(func):
            return func
        return decorator
    def get_thread_pool():
        return None

# Opus 常量
OPUS_OK = 0
OPUS_APPLICATION_VOIP = 2048
OPUS_APPLICATION_AUDIO = 2049
OPUS_APPLICATION_RESTRICTED_LOWDELAY = 2051

# 音频参数
SAMPLE_RATE = 48000  # 48kHz (Fullband)
FRAME_SIZE = 960     # 20ms @ 48kHz
CHANNELS = 1         # 单声道


class OpusDecoder:
    """Opus 解码器"""

    # 类级别 DLL 缓存: 首次加载后复用，避免重复磁盘 I/O
    _shared_lib = None
    _lib_configured = False  # 函数签名是否已配置

    @classmethod
    def _load_shared_lib(cls):
        """加载并缓存 Opus 库 (仅首次调用时执行磁盘 I/O)"""
        if cls._shared_lib is not None:
            return cls._shared_lib

        import platform
        system = platform.system()
        
        lib = None
        if system == "Windows":
            dll_path = os.path.join(os.path.dirname(__file__), "opus.dll")
            search_paths = [dll_path, "libopus-0.dll", "opus.dll"]
            for path in search_paths:
                try:
                    lib = ctypes.CDLL(path)
                    logger.info(f"[Opus] 已加载库: {path}")
                    break
                except OSError as e:
                    # 库加载失败，尝试下一个路径
                    continue
        elif system == "Darwin":  # macOS
            for path in ["libopus.0.dylib", "libopus.dylib"]:
                try:
                    lib = ctypes.CDLL(path)
                    logger.info(f"[Opus] 已加载库: {path}")
                    break
                except OSError as e:
                    continue
        else:  # Linux and others
            for path in ["libopus.so.0", "libopus.so"]:
                try:
                    lib = ctypes.CDLL(path)
                    logger.info(f"[Opus] 已加载库: {path}")
                    break
                except OSError as e:
                    continue

        if lib is None:
            logger.info("Warning: Could not load Opus library")
            return None

        # 配置函数签名 (只需一次)
        if not cls._lib_configured:
            lib.opus_decoder_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
            lib.opus_decoder_create.restype = ctypes.c_void_p
            lib.opus_decode.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32, ctypes.POINTER(ctypes.c_int16), ctypes.c_int, ctypes.c_int]
            lib.opus_decode.restype = ctypes.c_int
            lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
            lib.opus_decoder_destroy.restype = None
            cls._lib_configured = True

        cls._shared_lib = lib
        return lib

    def __init__(self, sample_rate=48000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._decoder = None
        self._lib = None

        # 使用缓存的 DLL 句柄 (首次调用时加载，后续直接复用)
        self._lib = self._load_shared_lib()
        if not self._lib:
            return

        try:
            error = ctypes.c_int()
            self._decoder = self._lib.opus_decoder_create(sample_rate, channels, ctypes.byref(error))
            if error.value != 0:
                 logger.info(f"Opus decoder init error: {error.value}")
                 self._decoder = None
            else:
                logger.info(f"[Opus] 解码器创建成功: {sample_rate}Hz")
        except Exception as e:
            logger.info(f"Error initializing Opus decoder: {e}")

    def decode(self, payload: bytes) -> bytes:
        """解码 Opus 数据为 PCM"""
        if not self._decoder:
            return b''

        try:
            # FRAME_SIZE = 960 (20ms) for 48kHz
            # MAX_FRAME_SIZE = 6 * 960 = 5760
            MAX_FRAME_SIZE = 5760
            pcm_buffer = (ctypes.c_int16 * (MAX_FRAME_SIZE * self.channels))()

            # Use cast to char p
            data_ptr = ctypes.c_char_p(payload)

            samples = self._lib.opus_decode(
                self._decoder,
                data_ptr,
                len(payload),
                pcm_buffer,
                MAX_FRAME_SIZE,
                0
            )

            if samples < 0:
                # specific error codes
                # logger.info(f"Opus decode error code: {samples}")
                return b''

            return ctypes.string_at(pcm_buffer, samples * self.channels * 2)

        except Exception as e:
            # logger.info(f"Decode exc: {e}")
            return b''

    def destroy(self):
        """销毁解码器"""
        if self._decoder and self._lib:
            self._lib.opus_decoder_destroy(self._decoder)
            self._decoder = None


class OpusEncoder:
    """Opus 编码器"""

    def __init__(self, sample_rate=48000, frame_size=960, bitrate=32000,
                 application=OPUS_APPLICATION_VOIP):
        """
        初始化 Opus 编码器

        Args:
            sample_rate: 采样率 (8000, 12000, 16000, 24000, 48000)
            frame_size: 帧大小 (采样数)
            bitrate: 比特率 (bps)
            application: 应用模式 (VOIP/AUDIO/RESTRICTED_LOWDELAY)
        """
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.bitrate = bitrate
        self.channels = CHANNELS

        self._encoder = None
        self._lib = None

        self._load_library()
        self._create_encoder(application)

    def _load_library(self):
        """加载 Opus 库"""
        import platform
        system = platform.system()

        if system == "Windows":
            # 使用绝对路径
            import os
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dll_path = os.path.join(base_dir, "opus.dll")
            search_paths = [os.path.abspath(dll_path), "libopus-0.dll", "opus.dll"]
        elif system == "Darwin":  # macOS
            search_paths = ["libopus.0.dylib", "libopus.dylib"]
        else:  # Linux
            search_paths = ["libopus.so.0", "libopus.so"]

        for lib_path in search_paths:
            try:
                self._lib = ctypes.CDLL(lib_path)
                logger.info(f"[Opus] 已加载库: {lib_path}")
                break
            except OSError:
                continue

        if not self._lib:
            raise RuntimeError("无法加载 Opus 库")

        # 配置函数签名
        # opus_encoder_create(Fs, channels, application, *error)
        self._lib.opus_encoder_create.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int)
        ]
        self._lib.opus_encoder_create.restype = ctypes.c_void_p

        # opus_encode(st, pcm, frame_size, data, max_data_bytes)
        self._lib.opus_encode.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int16),
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int
        ]
        self._lib.opus_encode.restype = ctypes.c_int

        # opus_encoder_destroy(st)
        self._lib.opus_encoder_destroy.argtypes = [ctypes.c_void_p]
        self._lib.opus_encoder_destroy.restype = None

        # opus_encoder_ctl(st, request, ...)
        self._lib.opus_encoder_ctl.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        self._lib.opus_encoder_ctl.restype = ctypes.c_int

    def _create_encoder(self, application: int):
        """创建编码器"""
        error = ctypes.c_int()

        self._encoder = self._lib.opus_encoder_create(
            self.sample_rate,
            self.channels,
            application,
            ctypes.byref(error)
        )

        if error.value != OPUS_OK:
            raise RuntimeError(f"创建 Opus 编码器失败, 错误码: {error.value}")

        # 设置比特率
        self.set_bitrate(self.bitrate)
        logger.info(f"[Opus] 编码器创建成功: {self.sample_rate}Hz, {self.bitrate}bps")

    def encode(self, pcm_data: np.ndarray) -> bytes:
        """
        编码 PCM 数据为 Opus

        Args:
            pcm_data: PCM 音频数据 (int16 数组, 长度必须等于 frame_size)

        Returns:
            编码后的 Opus 数据
        """
        if len(pcm_data) != self.frame_size:
            raise ValueError(
                f"PCM 数据长度错误: 期望 {self.frame_size}, 实际 {len(pcm_data)}"
            )

        if not self._encoder:
            raise RuntimeError("编码器未初始化")

        # 最大输出大小 (4000 bytes is safe for 20ms frame)
        MAX_PACKET_SIZE = 4000
        output_buffer = ctypes.create_string_buffer(MAX_PACKET_SIZE)

        # 确保 PCM 数据是 int16 类型
        if pcm_data.dtype != np.int16:
            pcm_data = pcm_data.astype(np.int16)

        # 编码
        encoded_bytes = self._lib.opus_encode(
            self._encoder,
            pcm_data.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
            self.frame_size,
            output_buffer,
            MAX_PACKET_SIZE
        )

        if encoded_bytes < 0:
            raise RuntimeError(f"编码失败, 错误码: {encoded_bytes}")

        return output_buffer.raw[:encoded_bytes]

    def set_bitrate(self, bitrate: int):
        """设置编码比特率"""
        # CTL request: OPUS_SET_BITRATE_REQUEST = 4002
        result = self._lib.opus_encoder_ctl(
            self._encoder,
            4002,  # OPUS_SET_BITRATE_REQUEST
            bitrate
        )

        if result == OPUS_OK:
            self.bitrate = bitrate

    def destroy(self):
        """销毁编码器"""
        if self._encoder and self._lib:
            self._lib.opus_encoder_destroy(self._encoder)
            self._encoder = None


class AudioRecorder:
    """简单的音频采集器 (阻塞模式)"""

    def __init__(self, sample_rate=48000, frame_size=960, channels=1):
        """初始化音频采集器"""
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.channels = channels

        self.pyaudio = None
        self.stream = None
        self.is_recording = False

        logger.info(f"[AudioRecorder] 初始化: {sample_rate}Hz")

    def _init_pyaudio(self):
        """初始化 PyAudio"""
        try:
            import pyaudio
            self.pyaudio = pyaudio.PyAudio()
            logger.info("[AudioRecorder] PyAudio 初始化成功")
            return True
        except ImportError:
            logger.info("[AudioRecorder] 错误: PyAudio 未安装")
            logger.info("                请运行: pip install pyaudio")
            return False
        except Exception as e:
            logger.info(f"[AudioRecorder] PyAudio 初始化失败: {e}")
            return False

    def start_recording(self) -> bool:
        """开始录音"""
        if self.is_recording:
            return True

        if not self._init_pyaudio():
            return False

        try:
            # 打开音频流 (阻塞模式)
            self.stream = self.pyaudio.open(
                format=self.pyaudio.get_format_from_width(2),  # 16-bit
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.frame_size
            )

            self.is_recording = True
            logger.info(f"[AudioRecorder] 开始录音: {self.sample_rate}Hz")
            return True

        except Exception as e:
            logger.info(f"[AudioRecorder] 启动录音失败: {e}")
            self.cleanup()
            return False

    def read_frame(self, timeout_ms=1000) -> Optional[np.ndarray]:
        """读取一帧音频数据 (阻塞)"""
        if not self.is_recording or not self.stream:
            return None

        try:
            # 读取音频数据
            # PyAudio 的 read() 是阻塞的，会自动等待 20ms (frame_size / sample_rate)
            data = self.stream.read(self.frame_size, exception_on_overflow=False)

            # 转换为 numpy 数组
            pcm_data = np.frombuffer(data, dtype=np.int16)

            return pcm_data

        except Exception as e:
            logger.info(f"[AudioRecorder] 读取音频失败: {e}")
            import traceback
            traceback.logger.info_exc()
            return None

    def stop_recording(self):
        """停止录音"""
        if not self.is_recording:
            return

        self.is_recording = False
        self.cleanup()
        logger.info("[AudioRecorder] 停止录音")

    def cleanup(self):
        """清理资源"""
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except (IOError, AttributeError) as e:
                # 忽略资源已关闭或无效句柄的错误
                pass
            self.stream = None

        if self.pyaudio:
            try:
                self.pyaudio.terminate()
            except Exception as e:
                # 忽略 PyAudio 终止错误
                pass
            self.pyaudio = None


class AudioPlayer:
    """简单的音频播放器 (阻塞模式)"""

    def __init__(self, sample_rate=48000, channels=1):
        """初始化音频播放器"""
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = 960

        self.pyaudio = None
        self.stream = None
        self.is_playing = False

        # 音量增益
        self.volume_gain = 1.0

        logger.info(f"[AudioPlayer] 初始化: {sample_rate}Hz")

    def _init_pyaudio(self):
        """初始化 PyAudio"""
        try:
            import pyaudio
            self.pyaudio = pyaudio.PyAudio()
            logger.info("[AudioPlayer] PyAudio 初始化成功")
            return True
        except ImportError:
            logger.info("[AudioPlayer] 错误: PyAudio 未安装")
            return False
        except Exception as e:
            logger.info(f"[AudioPlayer] PyAudio 初始化失败: {e}")
            return False

    def start_playback(self) -> bool:
        """开始播放"""
        if self.is_playing:
            return True

        if not self._init_pyaudio():
            return False

        try:
            # 打开音频流
            self.stream = self.pyaudio.open(
                format=self.pyaudio.get_format_from_width(2),  # 16-bit
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=self.frame_size
            )

            self.is_playing = True
            logger.info(f"[AudioPlayer] 开始播放: {self.sample_rate}Hz")
            return True

        except Exception as e:
            logger.info(f"[AudioPlayer] 启动播放失败: {e}")
            self.cleanup()
            return False

    def play(self, pcm_data: bytes):
        """
        播放音频帧 (阻塞)

        Args:
            pcm_data: PCM 音频数据 (bytes)
        """
        if not self.is_playing or not self.stream:
            return

        try:
            # 应用音量增益
            if self.volume_gain != 1.0:
                pcm_array = np.frombuffer(pcm_data, dtype=np.int16)
                pcm_array = (pcm_array.astype(np.float32) * self.volume_gain).astype(np.int16)
                pcm_data = pcm_array.tobytes()

            # 播放
            self.stream.write(pcm_data)

        except Exception as e:
            logger.info(f"[AudioPlayer] 播放失败: {e}")

    def set_volume_gain(self, gain: float):
        """设置音量增益"""
        self.volume_gain = max(0.1, min(2.0, gain))

    def stop_playback(self):
        """停止播放"""
        if not self.is_playing:
            return

        self.is_playing = False
        self.cleanup()
        logger.info("[AudioPlayer] 停止播放")

    def cleanup(self):
        """清理资源"""
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except (IOError, AttributeError) as e:
                # 忽略资源已关闭或无效句柄的错误
                pass
            self.stream = None

        if self.pyaudio:
            try:
                self.pyaudio.terminate()
            except Exception as e:
                # 忽略 PyAudio 终止错误
                pass
            self.pyaudio = None 


# ==================== PTT 控制器 ====================

class PTTState(Enum):
    """PTT 状态"""
    IDLE = "idle"
    PRESSED = "pressed"
    RECORDING = "recording"
    RELEASING = "releasing"


class PTTController:
    """PTT 控制器"""
    
    def __init__(self, recorder, encoder, player=None, 
                 on_audio_packet=None, on_state_change=None):
        self.recorder = recorder
        self.encoder = encoder
        self.player = player
        self.on_audio_packet = on_audio_packet
        self.on_state_change = on_state_change
        
        self.state = PTTState.IDLE
        self.is_pressed = False
        
        self.record_thread = None
        self.stop_event = threading.Event()
        
        self.frames_sent = 0
        self.total_bytes = 0
        self.start_time = 0
        self.duration = 0
        
        logger.info("[PTT] PTT 控制器初始化完成")
    
    def press(self):
        """PTT 按下"""
        if self.is_pressed:
            return
        
        self.is_pressed = True
        self._set_state(PTTState.PRESSED)
        
        if not self.recorder.is_recording:
            if not self.recorder.start_recording():
                logger.info("[PTT] 启动录音失败")
                self.is_pressed = False
                self._set_state(PTTState.IDLE)
                return
        
        if self.player and not self.player.is_playing:
            self.player.start_playback()
        
        self.stop_event.clear()
        self.record_thread = threading.Thread(target=self._record_loop, daemon=True)
        self.record_thread.start()
        
        self.frames_sent = 0
        self.total_bytes = 0
        self.start_time = time.time()
        
        logger.info("[PTT] PTT 按下 - 开始录音")
    
    def release(self):
        """PTT 释放"""
        if not self.is_pressed:
            return
        
        self.is_pressed = False
        self._set_state(PTTState.RELEASING)
        
        self.stop_event.set()
        
        if self.start_time > 0:
            self.duration = time.time() - self.start_time
        
        if self.record_thread:
            self.record_thread.join(timeout=1)
            self.record_thread = None
        
        self._send_stop_packet()
        
        self._set_state(PTTState.IDLE)
        
        logger.info(f"[PTT] PTT 释放 - 停止录音 (时长: {self.duration:.2f}s, 发送: {self.frames_sent} 帧)")
    
    def _record_loop(self):
        """录音循环"""
        self._set_state(PTTState.RECORDING)
        
        while not self.stop_event.is_set() and self.is_pressed:
            try:
                pcm_data = self.recorder.read_frame(timeout_ms=100)
                if pcm_data is None:
                    continue
                
                opus_data = self.encoder.encode(pcm_data)
                
                if self.on_audio_packet:
                    self.on_audio_packet(opus_data)
                    self.frames_sent += 1
                    self.total_bytes += len(opus_data)
                    
                    if self.frames_sent % 50 == 0:
                        elapsed = time.time() - self.start_time
                        logger.info(f"[PTT] 录音中: {elapsed:.1f}s, {self.frames_sent} 帧")
                        
            except Exception as e:
                if self.is_pressed:
                    logger.info(f"[PTT] 录音异常: {e}")
                break
    
    def _send_stop_packet(self):
        """发送停止包"""
        if self.on_audio_packet:
            self.on_audio_packet(b'')
            logger.info("[PTT] 发送停止包")
    
    def _set_state(self, state):
        """设置状态"""
        self.state = state
        if self.on_state_change:
            try:
                self.on_state_change(state)
            except Exception as e:
                # 忽略回调执行错误
                pass
    
    def get_stats(self):
        """获取统计"""
        duration = time.time() - self.start_time if self.start_time > 0 and self.is_pressed else self.duration
        return {
            'state': self.state.value,
            'is_pressed': self.is_pressed,
            'duration_seconds': duration,
            'frames_sent': self.frames_sent,
            'total_bytes': self.total_bytes
        }
    
    def cleanup(self):
        """清理"""
        if self.is_pressed:
            self.release()


class PTTControllerKeyboard:
    """键盘 PTT 控制器 (空格键)"""
    
    def __init__(self, recorder, encoder, player=None, on_audio_packet=None):
        self.ptt_controller = PTTController(
            recorder=recorder,
            encoder=encoder,
            player=player,
            on_audio_packet=on_audio_packet,
            on_state_change=self._on_state_change
        )
        self.is_listening = False
        
        logger.info("[PTT] 键盘 PTT 控制器初始化 (空格键)")
    
    def _on_state_change(self, state):
        """状态变化回调"""
        if state == PTTState.RECORDING:
            logger.info("[PTT] >>> 正在录音... (释放空格键停止)")
        elif state == PTTState.IDLE:
            logger.info("[PTT] || 已停止")
    
    def start(self):
        """开始监听键盘"""
        if self.is_listening:
            return
        
        self.is_listening = True
        logger.info("[PTT] 键盘监听已启动")
        logger.info("[PTT] 按住空格键说话, 释放停止")
        logger.info("[PTT] 按 Ctrl+C 退出")
        
        try:
            import keyboard
            
            space_pressed = False
            
            def on_press(key):
                nonlocal space_pressed
                if key == keyboard.Key.space or (hasattr(key, 'name') and key.name == 'space'):
                    if not space_pressed:
                        space_pressed = True
                        self.ptt_controller.press()
            
            def on_release(key):
                nonlocal space_pressed
                if key == keyboard.Key.space or (hasattr(key, 'name') and key.name == 'space'):
                    if space_pressed:
                        space_pressed = False
                        self.ptt_controller.release()
            
            keyboard.hook(on_press)
            keyboard.hook(on_release)
            
            keyboard.wait()
            
        except ImportError:
            logger.info("[PTT] 错误: keyboard 模块未安装")
            logger.info("       请运行: pip install keyboard")
            self.is_listening = False
        except Exception as e:
            logger.info(f"[PTT] 键盘监听失败: {e}")
            self.is_listening = False
    
    def stop(self):
        """停止监听"""
        if not self.is_listening:
            return
        
        self.is_listening = False
        
        try:
            import keyboard
            keyboard.unhook_all()
        except ImportError:
            # keyboard 模块未安装
            pass
        except Exception as e:
            # 忽略键盘清理错误
            pass
        
        self.ptt_controller.cleanup()
        logger.info("[PTT] 键盘监听已停止")
    
    def cleanup(self):
        """清理"""
        self.stop()
