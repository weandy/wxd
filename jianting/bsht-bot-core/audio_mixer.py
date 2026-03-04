"""
多用户音频混音器

为每个 SSRC (用户) 维护独立的 JitterBuffer + OpusDecoder，
从各用户缓冲区取帧、解码、混音输出。

结构:
  用户A → JitterBuffer_A → Decoder_A → PCM_A ─┐
  用户B → JitterBuffer_B → Decoder_B → PCM_B ─┤→ mix() → 播放
  用户C → JitterBuffer_C → Decoder_C → PCM_C ─┘
"""

import threading
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from jitter_buffer import JitterBuffer

logger = logging.getLogger("AudioMixer")


@dataclass
class UserStream:
    """单用户的音频流状态"""
    ssrc: int
    jitter_buf: 'JitterBuffer'
    decoder: object  # OpusDecoder
    last_frame_time: float = 0
    total_frames: int = 0
    total_lost: int = 0
    session_frames: int = 0
    session_lost: int = 0
    session_start: float = 0  # 第一帧到达时间
    session_end: float = 0    # 最后一帧到达时间
    is_active: bool = False
    session_ready: bool = False  # buffer是否积累够target_depth
    last_lost_count: int = 0  # 用于检测新增丢包
    first_sequence: int = None  # 第一帧序列号
    last_sequence: int = None   # 最后一帧序列号


class AudioMixer:
    """
    多用户音频混音器
    
    Usage:
        mixer = AudioMixer()
        
        # 接收线程中:
        mixer.push(ssrc, sequence, opus_data, marker)
        
        # 播放线程中:
        pcm = mixer.pop_mixed()  # 返回混合后的 PCM
        if pcm:
            stream.write(pcm)
    """
    
    FRAME_SIZE = 960          # 20ms @ 48kHz
    SILENCE_TIMEOUT = 0.3     # 0.3秒无数据 → 用户不再活跃 (降低延迟)
    STREAM_EXPIRE = 300.0     # 5分钟无数据 → 清理用户流 (保留解码器避免重建丢包)
    FRAME_DURATION = 0.02     # 每帧 20ms

    def __init__(self):
        self._streams: Dict[int, UserStream] = {}
        self._lock = threading.Lock()
        self._user_names: Dict[int, str] = {}  # ssrc → 昵称

        # 预生成静音帧
        self._silence_pcm = b'\x00' * (self.FRAME_SIZE * 2)  # 16bit mono

        # 统计回调 (每次通话结束时调用)
        self._on_session_end = None

        # 录制器
        self._recorder = None
        self._tx_recorder = None  # 发射录音器

        # 解码器预创建池: 避免首帧到达时才创建解码器导致的 300ms 延迟
        self._decoder_pool: list = []
        self._init_decoder_pool(3)  # 预创建 3 个解码器

    def _init_decoder_pool(self, count: int):
        """预创建解码器池"""
        try:
            from audio_codec import OpusDecoder
            for _ in range(count):
                self._decoder_pool.append(OpusDecoder(48000, 1))
            logger.info(f"解码器池已初始化: {count} 个")
        except Exception as e:
            logger.warning(f"解码器池初始化失败: {e}")

    def _get_decoder(self):
        """从池中获取解码器，池空时即时创建"""
        if self._decoder_pool:
            return self._decoder_pool.pop()
        from audio_codec import OpusDecoder
        return OpusDecoder(48000, 1)

    def _return_decoder(self, decoder):
        """回收解码器到池 (最多保留 5 个)"""
        if len(self._decoder_pool) < 5:
            self._decoder_pool.append(decoder)
    
    def set_user_names(self, names: Dict[int, str]):
        """设置/更新用户昵称映射"""
        self._user_names.update(names)
    
    def get_user_name(self, ssrc: int) -> str:
        """获取用户显示名"""
        return self._user_names.get(ssrc, f"用户({ssrc})")
    
    def set_session_callback(self, callback):
        """设置通话结束回调: callback(ssrc, duration, frames, lost, loss_pct)"""
        self._on_session_end = callback
    
    def set_recorder(self, recorder):
        """设置录制器 (ChannelRecorder 实例)"""
        self._recorder = recorder

    def set_tx_recorder(self, recorder):
        """设置发射录音器 (TX录音)"""
        self._tx_recorder = recorder
    
    def _get_or_create_stream(self, ssrc: int) -> UserStream:
        """获取或创建用户流 (内部使用，须持锁)"""
        if ssrc not in self._streams:
            self._streams[ssrc] = UserStream(
                ssrc=ssrc,
                jitter_buf=JitterBuffer(target_depth=3, max_depth=50),
                decoder=self._get_decoder(),  # 从池中取，零延迟
            )
        return self._streams[ssrc]
    
    def push(self, ssrc: int, sequence: int, opus_data: bytes, marker: bool = False):
        """
        将 RTP 帧推送到对应用户的 JitterBuffer

        Args:
            ssrc: 用户标识 (RTP SSRC = user_id)
            sequence: RTP 序列号
            opus_data: Opus 编码后的音频数据
            marker: RTP Marker 位 (指示通话开始)
        """
        with self._lock:
            us = self._get_or_create_stream(ssrc)

            # 用户变为活跃 (新 session 开始)
            if not us.is_active:
                us.is_active = True
                us.session_ready = False  # 等待buffer积累够target_depth
                us.jitter_buf.reset()     # 重置缓冲，重新同步序列号
                us.session_frames = 0
                us.session_lost = 0
                us.session_start = time.time()
                us.session_end = time.time()
                us.last_lost_count = 0
                us.first_sequence = sequence
                us.last_sequence = sequence
                logger.debug(f"[新session] ssrc={ssrc}, 首帧seq={sequence}, marker={marker}")

                # 通知录制器: 新通话开始
                if self._recorder:
                    name = self.get_user_name(ssrc)
                    self._recorder.on_speaker_start(ssrc, name)
            else:
                # 更新序列号范围
                us.last_sequence = sequence

            # 统一 push 帧
            us.jitter_buf.push(sequence, opus_data, ssrc, marker)
            us.last_frame_time = time.time()
            us.session_end = time.time()
    
    def pop_mixed(self) -> Optional[bytes]:
        """
        从所有活跃用户的 JitterBuffer 取帧 → 解码 → 混音
        
        Returns:
            混合后的 PCM bytes (960 samples, 16bit mono)
            如果没有活跃用户，返回 None
        """
        now = time.time()
        pcm_list: List[bytes] = []
        expired_sessions: List[Tuple[int, float, int, int, float]] = []
        
        with self._lock:
            # 检查新session的buffer是否准备好
            for us in self._streams.values():
                if us.is_active and not us.session_ready:
                    # 正常情况：达到目标深度
                    if us.jitter_buf.is_ready:
                        us.session_ready = True
                    else:
                        # 短突发语音兜底：缓冲里已有帧且已等待一小段时间，强制进入 session
                        # 避免短句永远达不到 target_depth 而导致不录制、不识别
                        buffered = us.jitter_buf.depth
                        waited = now - us.session_start if us.session_start else 0
                        if buffered > 0 and waited >= 0.08:
                            us.session_ready = True
                            logger.debug(f"[短突发兜底] ssrc={us.ssrc}, buffered={buffered}, waited={waited:.3f}s")
            
            active_ssrcs = [ssrc for ssrc, us in self._streams.items() 
                           if us.is_active and us.session_ready]
            
            if not active_ssrcs:
                return None
            
            for ssrc in active_ssrcs:
                us = self._streams[ssrc]
                frame = us.jitter_buf.pop()
                
                if frame is not None:
                    # 正常帧: 解码
                    pcm = us.decoder.decode(frame.opus_data)
                    if pcm:
                        pcm_list.append(pcm)
                        # 录制 PCM
                        if self._recorder:
                            self._recorder.write_pcm(ssrc, pcm)
                    us.last_frame_time = now
                    us.session_frames += 1
                    us.total_frames += 1
                    
                else:
                    # 检测新增丢包
                    current_lost = us.jitter_buf.total_lost
                    if current_lost > us.last_lost_count:
                        new_lost = current_lost - us.last_lost_count
                        
                        # 序列号大跳跃检测: 超过100帧的"丢包"实际是跨talkburst
                        # 自动重置JB开启新session，避免产生大量PLC静音
                        if new_lost > 100:
                            logger.info(f"[序列号跳跃] ssrc={ssrc}, 跳跃{new_lost}帧, 重置session")
                            us.jitter_buf.reset()
                            us.session_ready = False
                            us.session_frames = 0
                            us.session_lost = 0
                            us.last_lost_count = 0
                            us.session_start = time.time()
                            continue
                        
                        us.session_lost += new_lost
                        us.total_lost += new_lost
                        us.last_lost_count = current_lost
                        # PLC 补偿
                        pcm = us.decoder.decode(None)
                        if pcm:
                            pcm_list.append(pcm)
                        us.session_frames += 1

                    elif now - us.last_frame_time > self.SILENCE_TIMEOUT:
                        # 用户停止说话 → 计算准确时长
                        # 使用帧数计算时长，避免网络延迟和缓冲影响
                        duration = us.session_frames * self.FRAME_DURATION
                        total_expected = us.session_frames + us.session_lost
                        loss_pct = (us.session_lost / total_expected * 100) if total_expected > 0 else 0
                        expired_sessions.append((ssrc, duration, us.session_frames, us.session_lost, loss_pct))
                        us.is_active = False

                        # 通知录制器: 通话结束
                        if self._recorder:
                            self._recorder.on_speaker_end(ssrc, duration, us.session_frames, us.session_lost, loss_pct)

                    # else: 缓冲暂空但还在说话
        
        # 在锁外打印统计和调用回调
        for ssrc, duration, frames, lost, loss_pct in expired_sessions:
            name = self.get_user_name(ssrc)
            logger.info(f"[RX统计] {name}({ssrc}): {duration:.1f}s, "
                  f"{frames}帧播放, {lost}帧丢包, "
                  f"丢包率={loss_pct:.1f}%")
            if self._on_session_end:
                self._on_session_end(ssrc, duration, frames, lost, loss_pct)
        
        # 混音
        if not pcm_list:
            return None
        elif len(pcm_list) == 1:
            return pcm_list[0]
        else:
            return self._mix_pcm(pcm_list)
    
    def _mix_pcm(self, samples_list: List[bytes]) -> bytes:
        """
        混合多路 16bit PCM
        
        使用 numpy 进行高效混音:
        1. 各路 int16 转 int32 (防溢出)
        2. 求和
        3. clip 到 [-32768, 32767]
        4. 转回 int16
        """
        import numpy as np
        
        arrays = [np.frombuffer(s, dtype=np.int16) for s in samples_list]
        mixed = np.zeros(self.FRAME_SIZE, dtype=np.int32)
        for arr in arrays:
            if len(arr) == self.FRAME_SIZE:
                mixed += arr.astype(np.int32)
        mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
        return mixed.tobytes()
    
    @property
    def has_active_speakers(self) -> bool:
        """是否有活跃说话者"""
        with self._lock:
            return any(us.is_active for us in self._streams.values())
    
    def get_active_speakers(self) -> List[int]:
        """获取当前活跃说话者的 SSRC 列表"""
        with self._lock:
            return [ssrc for ssrc, us in self._streams.items() if us.is_active]
    
    def cleanup_expired(self):
        """清理长时间不活跃的用户流 (回收解码器到池)"""
        now = time.time()
        with self._lock:
            expired = [ssrc for ssrc, us in self._streams.items()
                      if not us.is_active and now - us.last_frame_time > self.STREAM_EXPIRE]
            for ssrc in expired:
                us = self._streams.pop(ssrc)
                # 回收解码器到池中复用，而非销毁
                self._return_decoder(us.decoder)
    
    @property
    def depth(self) -> int:
        """所有活跃用户buffer的最大深度"""
        with self._lock:
            depths = [us.jitter_buf.depth for us in self._streams.values() if us.is_active]
            return max(depths) if depths else 0

    def shutdown(self):
        """关闭混音器，释放所有资源"""
        logger.info("[AudioMixer] 正在关闭...")

        # 1. 清空所有用户流
        with self._lock:
            self._streams.clear()
            self._user_names.clear()

        # 2. 清空解码器池
        self._decoder_pool.clear()
        logger.info("[AudioMixer] 解码器池已清空")

        # 3. 清理录制器引用
        self._recorder = None
        self._tx_recorder = None

        logger.info("[AudioMixer] 已关闭")
