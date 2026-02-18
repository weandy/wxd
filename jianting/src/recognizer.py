"""
伪实时识别器 - 监听录音完成事件并进行识别
"""
import os
import sys
import threading
import logging
from typing import Optional, Callable
from datetime import datetime

# 添加路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

logger = logging.getLogger("Recognizer")


class RecordingRecognizer:
    """录音识别器 - 伪实时处理录音文件"""
    
    def __init__(self, api_key: str, dsp_config: dict = None):
        self.api_key = api_key
        self.dsp_config = dsp_config or {}
        self._processor = None
        self._db = None
        self._running = False
        self._lock = threading.Lock()
        self._pending_queue = []  # 待识别队列
        self._processing = False
    
    def set_database(self, db):
        """设置数据库实例"""
        self._db = db
    
    def _get_processor(self):
        """获取智能处理器"""
        if self._processor is None:
            from smart_processor import SmartAudioProcessor
            self._processor = SmartAudioProcessor(
                api_key=self.api_key,
                dsp_config=self.dsp_config
            )
        return self._processor
    
    def on_recording_complete(self, filepath: str, duration: float, 
                              start_time: str,
                              user_id: str, user_name: str,
                              channel_id: int, recorder_type: str):
        """录音完成回调 - 由 ChannelRecorder 调用"""
        if not os.path.exists(filepath):
            logger.warning(f"录音文件不存在: {filepath}")
            return
        
        # 检查文件大小
        file_size = os.path.getsize(filepath)
        if file_size <= 44:  # 空文件
            logger.debug(f"跳过空文件: {filepath}")
            return
        
        logger.info(f"📥 收到新录音: {os.path.basename(filepath)} "
                   f"用户={user_name}({user_id}) 时长={duration:.1f}s")
        
        # 添加到处理队列
        with self._lock:
            self._pending_queue.append({
                'filepath': filepath,
                'duration': duration,
                'start_time': start_time,
                'user_id': user_id,
                'user_name': user_name,
                'channel_id': channel_id,
                'recorder_type': recorder_type,
                'file_size': file_size,
                'timestamp': datetime.now().isoformat()
            })
        
        # 触发处理
        self._process_next()
    
    def _process_next(self):
        """处理下一个录音"""
        with self._lock:
            if self._processing or not self._pending_queue:
                return
            self._processing = True
            task = self._pending_queue.pop(0)
        
        # 后台处理
        threading.Thread(target=self._do_recognize, args=(task,), daemon=True).start()
    
    def _calculate_duration(self, filepath: str) -> float:
        """从WAV文件计算时长"""
        try:
            import wave
            with wave.open(filepath, 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return frames / rate if rate > 0 else 0
        except Exception as e:
            logger.warning(f"计算时长失败: {e}")
            return 0
    
    def get_pending_count(self) -> int:
        """获取待处理队列数量"""
        with self._lock:
            return len(self._pending_queue) + (1 if self._processing else 0)
    
    def _do_recognize(self, task: dict):
        """执行识别"""
        filepath = task['filepath']
        duration = task['duration']
        start_time = task.get('start_time', '')  # 开始录音时间
        user_id = task['user_id']
        user_name = task['user_name']
        channel_id = task['channel_id']
        recorder_type = task['recorder_type']
        file_size = task['file_size']
        timestamp = task['timestamp']
        
        # 如果时长为0，从文件计算
        if duration <= 0:
            duration = self._calculate_duration(filepath)
            logger.info(f"计算时长: {filepath} -> {duration:.2f}s")
        
        logger.info(f"开始识别: {os.path.basename(filepath)}, 时长={duration:.2f}s, 开始时间={start_time}")
        
        # 时长过滤：低于1秒的录音标记为无效，不上传云端识别
        if duration < 1.0:
            logger.info(f"录音时长 {duration:.2f}s < 1s，标记为无效")
            if self._db:
                self._db.update_recording_recognition(
                    filepath=filepath,
                    asr_text="",
                    content_normalized="",
                    signal_type="INVALID",
                    confidence=0,
                    rms_db=0,
                    snr_db=0
                )
            logger.info(f"✅ 标记为无效: {os.path.basename(filepath)}")
            with self._lock:
                self._processing = False
            self._process_next()
            return
        
        try:
            # 先添加到数据库
            if self._db:
                from database import Recording
                rec = Recording(
                    filepath=filepath,
                    filename=os.path.basename(filepath),
                    channel_id=channel_id,
                    user_id=user_id,
                    user_name=user_name,
                    recorder_type=recorder_type,
                    duration=round(duration, 1),  # 精确到0.1秒
                    start_time=start_time,
                    file_size=file_size,
                    timestamp=timestamp,
                    recognized=False
                )
                rec_id = self._db.add_recording(rec)
                logger.info(f"录音记录已添加: ID={rec_id}")
            
            # 执行识别
            processor = self._get_processor()
            ai_result, quality, suggestion = processor.process(filepath)
            
            # 打印识别结果
            self._print_result(ai_result, quality, suggestion, user_name, recorder_type)
            
            # 更新数据库
            if self._db:
                self._db.update_recording_recognition(
                    filepath=filepath,
                    asr_text=ai_result.content,
                    content_normalized=ai_result.content_normalized,
                    signal_type=ai_result.signal_type,
                    confidence=ai_result.confidence,
                    rms_db=quality.rms_db,
                    snr_db=quality.snr_db
                )
            
            logger.info(f"✅ 识别完成: {os.path.basename(filepath)}")
            
        except Exception as e:
            logger.error(f"识别失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 标记为识别失败
            if self._db:
                try:
                    self._db.update_recording_recognition(
                        filepath=filepath,
                        asr_text=f"识别失败: {str(e)}",
                        content_normalized="",
                        signal_type="ERROR",
                        confidence=0,
                        rms_db=0,
                        snr_db=0
                    )
                except:
                    pass
        
        # 无论成功还是失败，都继续处理队列
        with self._lock:
            self._processing = False
        self._process_next()
    
    def _print_result(self, ai_result, quality, suggestion, user_name, recorder_type):
        """打印识别结果到控制台"""
        type_icon = {"CQ": "📡", "QSO": "📱", "CQ73": "📡", "QRZ": "📶", "NOISE": "🔇", "UNKNOWN": "❓"}
        icon = type_icon.get(ai_result.signal_type, "❓")
        
        print("\n" + "=" * 60)
        print(f"🎙️ [{recorder_type}] {user_name}")
        print("-" * 60)
        
        # 音频质量
        print(f"   📊 SNR: {quality.snr_db:.1f} dB | 时长: {quality.duration:.1f}s")
        
        # DSP处理
        print(f"   🔊 DSP: {'是' if suggestion.needed else '否'} ({suggestion.level})")
        
        # 识别结果 - 优先使用规范化后的内容
        if ai_result.success and ai_result.content:
            # 显示规范化内容(如果与原始不同)
            display_content = ai_result.content_normalized if ai_result.content_normalized else ai_result.content
            print(f"   {icon} {ai_result.signal_type}: {display_content}")
            
            # 如果有呼号识别，显示出来
            if ai_result.user_id:
                print(f"   📻 呼号: {ai_result.user_id}")
            
            conf = ai_result.confidence
            conf_color = "🟢" if conf > 0.8 else "🟡" if conf > 0.5 else "🔴"
            print(f"   {conf_color} 置信度: {conf*100:.1f}%")
        else:
            print(f"   ❌ 识别失败: {ai_result.error}")
        
        print("=" * 60)
    
    def process_existing_recordings(self, base_dir: str = "recordings", 
                                     max_count: int = 50):
        """处理已存在的录音文件 (批量识别)"""
        logger.info(f"扫描已有录音: {base_dir}")
        
        processed = 0
        for root, dirs, files in os.walk(base_dir):
            for filename in files:
                if not filename.endswith('.wav'):
                    continue
                
                filepath = os.path.join(root, filename)
                
                # 检查是否已识别
                if self._db:
                    existing = self._db.get_recording_by_path(filepath)
                    if existing and existing.recognized:
                        continue
                
                # 获取文件信息
                file_size = os.path.getsize(filepath)
                if file_size <= 44:
                    continue
                
                # 解析文件名: 001_123456_153045.wav
                parts = filename.replace('.wav', '').split('_')
                if len(parts) >= 3:
                    user_id = parts[1]
                else:
                    user_id = "unknown"
                
                logger.info(f"处理: {filename}")
                
                # 触发识别
                self.on_recording_complete(
                    filepath=filepath,
                    duration=0,  # 需要从文件计算
                    user_id=user_id,
                    user_name=user_id,
                    channel_id=0,
                    recorder_type="RX"
                )
                
                processed += 1
                if processed >= max_count:
                    logger.info(f"已达到最大处理数量: {max_count}")
                    break
            
            if processed >= max_count:
                break
        
        logger.info(f"已添加到处理队列: {processed} 个文件")


def create_recording_callback(recognizer):
    """创建录音完成回调函数"""
    def callback(filepath: str, duration: float, user_id: str, 
                user_name: str, channel_id: int, recorder_type: str):
        recognizer.on_recording_complete(
            filepath=filepath,
            duration=duration,
            user_id=user_id,
            user_name=user_name,
            channel_id=channel_id,
            recorder_type=recorder_type
        )
    return callback
