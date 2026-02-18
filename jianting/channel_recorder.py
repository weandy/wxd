"""
频道对话录制器

持续录制频道内的所有音频对话:
- 每段 PTT 通话 = 一个 WAV 文件
- 按日期组织文件夹
- conversation_log.json 记录完整时间线

存储结构:
  recordings/
  └── 2026-02-17/
      ├── conversation_log.json
      ├── 频道A_用户X_15-10-41.wav
      ├── 频道A_用户Y_15-10-45.wav
      └── 频道B_用户Z_15-11-02.wav
"""

import os
import json
import wave
import time
import threading
import logging
from datetime import datetime
from typing import Dict, Optional
from audio_processor import AudioProcessor

# 初始化日志
logger = logging.getLogger("ChannelRecorder")


class ChannelRecorder:
    """
    频道对话录制器
    
    接入 AudioMixer 的回调，将解码后的 PCM 写入 WAV 文件。
    
    Usage:
        recorder = ChannelRecorder(channel_id=62793)
        
        # 在 AudioMixer 中:
        mixer.set_recorder(recorder)
        
        # 或手动调用:
        recorder.on_speaker_start(ssrc=123, name="用户A")
        recorder.write_pcm(ssrc=123, pcm_data=b'...')
        recorder.on_speaker_end(ssrc=123, duration=5.0, ...)
    """
    
    SAMPLE_RATE = 48000
    CHANNELS = 1
    SAMPLE_WIDTH = 2  # 16-bit = 2 bytes

    def __init__(self, base_dir: str = "recordings", channel_id: int = 0,
                 channel_name: str = "", recorder_type: str = "",
                 audio_processor: AudioProcessor = None,
                 on_recording_complete=None):
        # 统一目录结构: recordings/日期/
        self._base_dir = base_dir
        self._channel_id = channel_id
        self._channel_name = self._sanitize_name(channel_name) if channel_name else f"ch{channel_id}"
        self._lock = threading.Lock()

        # 录音器类型
        if recorder_type:
            self._recorder_type = recorder_type
        else:
            self._recorder_type = "TX" if "/tx" in base_dir.replace("\\", "/") else "RX"
        self._logger = logging.getLogger(f"ChannelRecorder.{self._recorder_type}")
        
        # 音频预处理器 (对讲机优化: 滤波+归一化)
        self._processor = audio_processor
        
        # 录音完成回调: callback(filepath, duration, user_id, user_name)
        self._on_recording_complete = on_recording_complete
        
        # 当前活跃的录制会话: ssrc → ActiveRecording
        self._active: Dict[int, '_ActiveRecording'] = {}
        
        # 当天的录制序号
        self._today_str = ""
        self._today_seq = 0
        
        # 确保基础目录存在
        os.makedirs(base_dir, exist_ok=True)
        proc_info = " (含音频预处理)" if self._processor else ""
        self._logger.info(f"[{self._recorder_type}] 录制器已启动, 频道={self._channel_name}, 路径: {os.path.abspath(base_dir)}{proc_info}")
    
    def _get_today_dir(self) -> str:
        """获取/创建当天日期文件夹, 如果日期变化则重置序号"""
        today = datetime.now().strftime("%Y-%m-%d")
        dir_path = os.path.join(self._base_dir, today)
        
        if today != self._today_str:
            self._today_str = today
            # 扫描已有文件确定起始序号
            self._today_seq = self._scan_existing_seq(dir_path)
        
        os.makedirs(dir_path, exist_ok=True)
        return dir_path
    
    def _scan_existing_seq(self, dir_path: str) -> int:
        """扫描已有录制文件，返回下一个可用序号"""
        max_seq = 0
        if os.path.exists(dir_path):
            for f in os.listdir(dir_path):
                if f.endswith('.wav') and '_' in f:
                    try:
                        seq = int(f.split('_')[0])
                        max_seq = max(max_seq, seq)
                    except (ValueError, IndexError):
                        pass
        return max_seq
    
    def _next_seq(self) -> int:
        """获取下一个序号 (线程安全, 需持锁)"""
        self._today_seq += 1
        return self._today_seq
    
    def _sanitize_name(self, name: str) -> str:
        """清理用户名中不适合做文件名的字符"""
        invalid_chars = '<>:"/\\|?*'
        result = name
        for c in invalid_chars:
            result = result.replace(c, '_')
        return result[:30]  # 限制长度
    
    def on_speaker_start(self, ssrc: int, name: str = ""):
        """
        说话者开始说话 → 创建新 WAV 文件
        
        Args:
            ssrc: 用户 SSRC
            name: 用户昵称
        """
        with self._lock:
            # 如果此用户已有活跃录制, 先关闭
            if ssrc in self._active:
                self._close_recording(ssrc)
            
            today_dir = self._get_today_dir()
            seq = self._next_seq()
            now = datetime.now()
            time_str = now.strftime("%H%M%S")
            display_name = name if name else f"用户{ssrc}"
            user_id = str(ssrc)  # 使用SSRC作为用户ID
            
            # 文件名格式: 序号_用户ID_时间.wav (如: 001_123456_153045.wav)
            base_name = f"{seq:03d}_{user_id}_{time_str}"
            filename = f"{base_name}.wav"
            filepath = os.path.join(today_dir, filename)
            
            try:
                wf = wave.open(filepath, 'wb')
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(self.SAMPLE_WIDTH)
                wf.setframerate(self.SAMPLE_RATE)
                
                self._active[ssrc] = _ActiveRecording(
                    ssrc=ssrc,
                    name=display_name,
                    user_id=user_id,
                    filename=filename,
                    filepath=filepath,
                    wav_file=wf,
                    start_time=now,
                    seq=seq,
                    frame_count=0
                )

                self._logger.info(f"[{self._recorder_type}] 开始录制: {filename}")

            except Exception as e:
                self._logger.error(f"创建WAV文件失败: {e}")
    
    def write_pcm(self, ssrc: int, pcm_data: bytes):
        """
        写入 PCM 数据到对应用户的 WAV 文件
        
        Args:
            ssrc: 用户 SSRC
            pcm_data: 解码后的 PCM 数据 (16bit mono 48kHz)
        """
        with self._lock:
            rec = self._active.get(ssrc)
            if rec and rec.wav_file and pcm_data:
                try:
                    # 音频预处理 (高通滤波 + AGC)
                    data = self._processor.process(pcm_data) if self._processor else pcm_data
                    rec.wav_file.writeframes(data)
                    rec.frame_count += 1
                except Exception as e:
                    self._logger.error(f"写入PCM数据失败 ({rec.filename}): {e}")
    
    def on_speaker_end(self, ssrc: int, duration: float = 0, 
                       frames: int = 0, lost: int = 0, loss_pct: float = 0):
        """
        说话者停止说话 → 关闭 WAV 文件, 更新日志
        
        Args:
            ssrc: 用户 SSRC
            duration: 通话时长(秒)
            frames: 播放帧数
            lost: 丢包帧数
            loss_pct: 丢包率(%)
        """
        with self._lock:
            self._close_recording(ssrc, duration, frames, lost, loss_pct)
    
    def _close_recording(self, ssrc: int, duration: float = 0,
                          frames: int = 0, lost: int = 0, loss_pct: float = 0):
        """关闭录制 (内部使用, 须持锁)"""
        rec = self._active.pop(ssrc, None)
        if not rec:
            return
        
        end_time = datetime.now()
        
        # 关闭 WAV 文件
        try:
            if rec.wav_file:
                rec.wav_file.close()
        except Exception as e:
            logger.error(f"关闭WAV文件失败 ({rec.filename}): {e}")

        # 如果没传 duration, 自己计算
        if duration <= 0:
            duration = (end_time - rec.start_time).total_seconds()

        # 检查文件是否有内容
        file_size = 0
        try:
            file_size = os.path.getsize(rec.filepath)
        except Exception as e:
            logger.warning(f"获取文件大小失败 ({rec.filepath}): {e}")

        if file_size <= 44:  # WAV 头 = 44 bytes, 无实际数据
            # 删除空文件
            try:
                os.remove(rec.filepath)
            except Exception as e:
                logger.warning(f"删除空文件失败 ({rec.filepath}): {e}")
            return

        file_size_kb = file_size / 1024
        self._logger.info(f"[{self._recorder_type}] 录制完成: {rec.filename} ({duration:.1f}s, {file_size_kb:.0f}KB)")

        # 写入 conversation_log
        self._append_log(rec, end_time, duration, frames, lost, loss_pct)
        
        # 触发录音完成回调 (用于伪实时识别)
        if self._on_recording_complete:
            try:
                self._on_recording_complete(
                    filepath=rec.filepath,
                    duration=duration,
                    user_id=rec.user_id,
                    user_name=rec.name,
                    channel_id=self._channel_id,
                    recorder_type=self._recorder_type
                )
            except Exception as e:
                self._logger.error(f"录音完成回调失败: {e}")
    
    def _append_log(self, rec: '_ActiveRecording', end_time: datetime,
                    duration: float, frames: int, lost: int, loss_pct: float):
        """追加一条记录到 conversation_log.json"""
        today_dir = self._get_today_dir()
        log_path = os.path.join(today_dir, "conversation_log.json")
        
        # 读取已有记录
        log_data = {
            "date": self._today_str,
            "channel_id": self._channel_id,
            "recordings": []
        }
        
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
            except Exception as e:
                self._logger.warning(f"读取现有日志文件失败: {e}")

        # 添加新记录
        entry = {
            "id": rec.seq,
            "file": rec.filename,
            "speaker_ssrc": rec.ssrc,
            "speaker_name": rec.name,
            "start_time": rec.start_time.strftime("%H:%M:%S"),
            "end_time": end_time.strftime("%H:%M:%S"),
            "duration_sec": round(duration, 1),
            "frames": frames,
            "lost_frames": lost,
            "loss_rate": round(loss_pct, 1)
        }
        log_data["recordings"].append(entry)

        # 写入
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._logger.error(f"写入日志文件失败 ({log_path}): {e}")
    
    def close_all(self):
        """关闭所有活跃录制 (程序退出时调用)"""
        with self._lock:
            for ssrc in list(self._active.keys()):
                self._close_recording(ssrc)
        self._logger.info(f"[{self._recorder_type}] 所有录制已关闭")


class _ActiveRecording:
    """活跃的录制会话"""
    
    __slots__ = ['ssrc', 'name', 'user_id', 'filename', 'filepath', 'wav_file', 
                 'start_time', 'seq', 'frame_count']
    
    def __init__(self, ssrc: int, name: str, user_id: str, filename: str, filepath: str,
                 wav_file, start_time: datetime, seq: int, frame_count: int):
        self.ssrc = ssrc
        self.name = name
        self.user_id = user_id
        self.filename = filename
        self.filepath = filepath
        self.wav_file = wav_file
        self.start_time = start_time
        self.seq = seq
        self.frame_count = frame_count
