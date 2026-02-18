"""
伪实时识别器 - 监听录音完成事件并进行识别
"""
import os
import sys
import threading
import logging
from typing import Optional, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future
import time

# 添加路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# 使用日志配置模块
from logging_setup import setup_logger
logger = setup_logger("Recognizer", "recognize")


class RecordingRecognizer:
    """录音识别器 - 伪实时处理录音文件，支持并发识别"""
    
    def __init__(self, api_key: str, dsp_config: dict = None):
        self.api_key = api_key
        self.dsp_config = dsp_config or {}
        self._processor = None
        self._db = None
        self._running = False
        self._lock = threading.Lock()
        self._pending_queue = []  # 待识别队列
        self._processing = False
        
        # 并发识别配置
        max_workers = int(dsp_config.get("max_concurrent_workers", 3)) if dsp_config else 3
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._active_futures = set()  # 跟踪活跃的识别任务
        logger.info(f"[并发识别] 线程池初始化: {max_workers} 个工作线程")
    
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
        """处理下一个录音 - 使用线程池并发"""
        with self._lock:
            if not self._pending_queue:
                return
            task = self._pending_queue.pop(0)
        
        # 使用线程池提交任务
        future = self._executor.submit(self._do_recognize, task)
        future.add_done_callback(lambda f: self._on_task_done(f, task))
        
        with self._lock:
            self._active_futures.add(future)
    
    def _on_task_done(self, future: Future, task: dict):
        """任务完成回调"""
        with self._lock:
            self._active_futures.discard(future)
        
        # 处理异常
        try:
            future.result()
        except Exception as e:
            logger.error(f"[{task.get('filepath', 'unknown')}] 识别异常: {e}")
        
        # 继续处理队列
        self._process_next()
    
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
            return len(self._pending_queue) + len(self._active_futures)
    
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
        
        # 获取无效音频时长阈值配置 - 去除注释部分
        import os as os_module
        env_val = os_module.getenv('INVALID_AUDIO_DURATION', '1.0')
        # 去除注释（如 "1.0  # 注释" -> "1.0"）
        env_val = env_val.split('#')[0].strip()
        try:
            invalid_duration_threshold = float(env_val) if env_val else 1.0
        except ValueError:
            invalid_duration_threshold = 1.0
        
        logger.info(f"开始识别: {os.path.basename(filepath)}, 时长={duration:.2f}s, 开始时间={start_time}")
        
        # 时长过滤：低于阈值的录音标记为无效，但仍存储
        if invalid_duration_threshold > 0 and duration < invalid_duration_threshold:
            logger.info(f"录音时长 {duration:.2f}s < {invalid_duration_threshold}s，标记为无效")
            if self._db:
                self._db.update_recording_recognition(
                    filepath=filepath,
                    asr_text="",
                    content_normalized="",
                    signal_type="INVALID",
                    confidence=0,
                    rms_db=0,
                    snr_db=0,
                    invalid_reason="duration_too_short"
                )
            logger.info(f"✅ 标记为无效: {os.path.basename(filepath)}")
            return
        
        # ===== 数据库缓存检查 =====
        if self._db:
            existing = self._db.get_recording_by_path(filepath)
            if existing and existing.recognized:
                logger.info(f"[缓存] 使用已识别结果: {os.path.basename(filepath)}")
                # 从数据库恢复识别结果并打印
                from dataclasses import dataclass
                @dataclass
                class AIResult:
                    content: str = ""
                    content_normalized: str = ""
                    signal_type: str = "UNKNOWN"
                    confidence: float = 0.5
                    user_id: str = ""
                
                @dataclass  
                class AudioQuality:
                    rms_db: float = 0.0
                    snr_db: float = 0.0
                
                ai_result = AIResult(
                    content=existing.asr_text or "",
                    content_normalized=existing.content_normalized or "",
                    signal_type=existing.signal_type or "UNKNOWN",
                    confidence=existing.confidence or 0.5
                )
                quality = AudioQuality(
                    rms_db=existing.rms_db or 0.0,
                    snr_db=existing.snr_db or 0.0
                )
                suggestion = ""
                
                self._print_result(ai_result, quality, suggestion, user_name, recorder_type, 
                                  existing.asr_text or "", existing.recognize_duration or 0, 
                                  start_time, self.dsp_config.get("expert_model", "N/A"))
                logger.info(f"[缓存] 识别完成: {os.path.basename(filepath)} (from cache)")
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
            
            # 执行识别并记录耗时
            import time
            start_time_recognize = time.time()
            
            processor = self._get_processor()
            ai_result, quality, suggestion = processor.process(filepath)
            
            recognize_duration = time.time() - start_time_recognize
            
            # 获取使用的专家模型
            expert_model = self.dsp_config.get("expert_model", "Qwen/Qwen2.5-7B-Instruct")
            
            # 保存原始ASR结果用于显示
            asr_raw = ai_result.content
            
            # 打印识别结果
            self._print_result(ai_result, quality, suggestion, user_name, recorder_type, asr_raw, recognize_duration, start_time, expert_model)
            
            # 更新数据库
            if self._db:
                self._db.update_recording_recognition(
                    filepath=filepath,
                    asr_text=ai_result.content,
                    content_normalized=ai_result.content_normalized,
                    signal_type=ai_result.signal_type,
                    confidence=ai_result.confidence,
                    rms_db=quality.rms_db,
                    snr_db=quality.snr_db,
                    recognize_duration=recognize_duration
                )
            
            logger.info(f"✅ 识别完成: {os.path.basename(filepath)}, 耗时: {recognize_duration:.2f}s")
            
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
        
        # 无论成功还是失败，都由callback处理队列
        pass
    
    def _print_result(self, ai_result, quality, suggestion, user_name, recorder_type, asr_raw="", recognize_duration=0.0, start_time="", expert_model=""):
        """打印识别结果到控制台"""
        type_icon = {"CQ": "📡", "QSO": "📱", "CQ73": "📡", "QRZ": "📶", "NOISE": "🔇", "UNKNOWN": "❓"}
        icon = type_icon.get(ai_result.signal_type, "❓")
        
        print("\n" + "=" * 60)
        # 显示时间戳和类型
        time_info = f"🕐 {start_time}" if start_time else ""
        print(f"🎙️ [{recorder_type}] {user_name} {time_info}")
        print("-" * 60)
        
        # 显示使用的模型
        if expert_model:
            print(f"   🤖 专家模型: {expert_model}")
        
        # 音频质量
        print(f"   📊 SNR: {quality.snr_db:.1f} dB | 时长: {quality.duration:.1f}s")
        
        # 识别耗时
        if recognize_duration > 0:
            print(f"   ⏱️ 识别耗时: {recognize_duration:.2f}s")
        
        # DSP处理
        print(f"   🔊 DSP: {'是' if suggestion.needed else '否'} ({suggestion.level})")
        
        # SenseVoice识别结果
        if ai_result.sensevoice_content:
            print(f"   🎯 SenseVoice: {ai_result.sensevoice_content}")
        
        # Qwen专家模型识别结果
        if ai_result.expert_content:
            print(f"   🧠 Qwen识别: {ai_result.expert_content}")
        
        # 识别结果 - 优先使用规范化后的内容
        if ai_result.success and ai_result.content:
            # 显示规范化内容(如果与原始不同)
            display_content = ai_result.content_normalized if ai_result.content_normalized else ai_result.content
            print(f"   {icon} {ai_result.signal_type}: {display_content}")
            
            # 如果有呼号识别，显示出来
            if ai_result.user_id:
                print(f"   📻 呼号: {ai_result.user_id}")
            
            # 确保confidence是浮点数
            try:
                conf = float(ai_result.confidence)
            except (ValueError, TypeError):
                conf = 0.5
            conf_color = "🟢" if conf > 0.8 else "🟡" if conf > 0.5 else "🔴"
            print(f"   {conf_color} 置信度: {conf*100:.1f}%")
        else:
            print(f"   ❌ 识别失败: {ai_result.error}")
        
        print("=" * 60)
    
    def scan_and_register_recordings(self, base_dir: str = "recordings", 
                                      max_count: int = 100):
        """扫描录音目录，将未入库的文件添加到数据库，并识别未处理的
        
        1. 首先扫描所有音频文件
        2. 将不在数据库中的文件添加到数据库
        3. 对未识别的文件进行识别（低于时长的直接标记无效）
        """
        import re
        import wave
        import os as os_module
        
        logger.info(f"[扫描] 开始扫描录音目录: {base_dir}")
        
        # 获取无效音频时长阈值 - 去除注释部分
        env_val = os_module.getenv('INVALID_AUDIO_DURATION', '1.0')
        env_val = env_val.split('#')[0].strip()
        try:
            invalid_duration_threshold = float(env_val) if env_val else 1.0
        except ValueError:
            invalid_duration_threshold = 1.0
        logger.info(f"[扫描] 无效音频时长阈值: {invalid_duration_threshold}s")
        
        # 第一步：找出所有需要入库的文件
        files_to_add = []  # [(filepath, filename, status, duration, timestamp)]
        for root, dirs, files in os.walk(base_dir):
            for filename in files:
                if not filename.endswith('.wav'):
                    continue
                
                filepath = os.path.join(root, filename)
                
                # 检查文件是否存在
                file_size = os.path.getsize(filepath)
                if file_size <= 44:  # 跳过空文件
                    continue
                
                # 从路径获取日期时间作为 start_time
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filepath)
                timestamp = date_match.group(1) if date_match else ""
                
                # 计算音频时长
                try:
                    with wave.open(filepath, 'rb') as wf:
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        duration = frames / float(rate)
                except:
                    duration = 0.0
                
                # 检查是否已在数据库中
                if self._db:
                    existing = self._db.get_recording_by_path(filepath)
                    if existing:
                        # 已在数据库中，检查是否需要识别
                        if not existing.recognized and existing.invalid_reason == "":
                            # 需要识别但还未识别，加入队列
                            files_to_add.append((filepath, filename, "needs_recognition", duration, timestamp))
                        continue
                
                # 不在数据库中，需要添加
                files_to_add.append((filepath, filename, "new", duration, timestamp))
        
        logger.info(f"[扫描] 发现 {len(files_to_add)} 个需要处理的文件")
        
        # 第二步：将新文件添加到数据库（低于时长的直接标记无效）
        added_count = 0
        recognized_count = 0
        for filepath, filename, status, duration, timestamp in files_to_add:
            if status == "new":
                # 解析文件名获取用户信息
                parts = filename.replace('.wav', '').split('_')
                user_id = parts[1] if len(parts) >= 3 else "unknown"
                
                # 检查时长是否低于阈值
                if invalid_duration_threshold > 0 and duration > 0 and duration < invalid_duration_threshold:
                    # 时长不足，标记为无效
                    logger.info(f"[扫描] 时长不足({duration:.1f}s < {invalid_duration_threshold}s): {filename}")
                    if self._db:
                        from src.database import Recording
                        recording = Recording(
                            filepath=filepath,
                            filename=filename,
                            channel_id=0,
                            user_id=user_id,
                            user_name=user_id,
                            recorder_type="RX",
                            duration=duration,
                            start_time=timestamp,
                            file_size=os.path.getsize(filepath),
                            timestamp=timestamp,
                            recognized=True,  # 已处理
                            invalid_reason="duration_too_short"
                        )
                        self._db.add_recording(recording)
                        added_count += 1
                else:
                    # 时长正常，添加到数据库待识别
                    if self._db:
                        from src.database import Recording
                        recording = Recording(
                            filepath=filepath,
                            filename=filename,
                            channel_id=0,
                            user_id=user_id,
                            user_name=user_id,
                            recorder_type="RX",
                            duration=duration,
                            start_time=timestamp,
                            file_size=os.path.getsize(filepath),
                            timestamp=timestamp,
                            recognized=False
                        )
                        self._db.add_recording(recording)
                        added_count += 1
                        # 触发识别
                        logger.info(f"[扫描] 识别: {filename} ({duration:.1f}s)")
                        self.on_recording_complete(
                            filepath=filepath,
                            duration=duration,
                            start_time=timestamp,
                            user_id=user_id,
                            user_name=user_id,
                            channel_id=0,
                            recorder_type="RX"
                        )
                        recognized_count += 1
                        if recognized_count >= max_count:
                            logger.info(f"[扫描] 已达到最大处理数量: {max_count}")
                            break
        
        logger.info(f"[扫描] 完成: 新增 {added_count} 条记录, 识别 {recognized_count} 个文件")
        return added_count, recognized_count
    
    def process_existing_recordings(self, base_dir: str = "recordings", 
                                     max_count: int = 50):
        """处理已存在的录音文件 (批量识别) - 兼容旧接口"""
        return self.scan_and_register_recordings(base_dir, max_count)


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
