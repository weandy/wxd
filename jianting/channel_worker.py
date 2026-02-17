"""
单频道工作线程

纯监听模式: UDP 接收 → Opus 解码 → WAV 录音
不需要 PyAudio (不播放不录音), 适合云服务器无声卡环境

每个 ChannelWorker 独立运行:
  - 自己的 AudioStreamListener (UDP socket)
  - 自己的 AudioMixer (JitterBuffer + Decoder)
  - 自己的 ChannelRecorder (WAV 文件)
"""

import time
import threading
import logging
from typing import Optional, Dict, Callable

logger = logging.getLogger("ChannelWorker")


class ChannelWorker:
    """
    单频道监听+录音工作线程
    
    Usage:
        from bsht_client import BSHTClient
        
        client = BSHTClient()
        client.login("user", "pass")
        
        worker = ChannelWorker(
            client=client,
            channel_id=28951,
            channel_name="测试频道",
        )
        worker.start()
        # ...
        worker.stop()
    """
    
    # 保活心跳间隔 (秒)
    HEARTBEAT_INTERVAL = 30
    # 说话者超时 (秒)
    SPEAKER_TIMEOUT = 0.5
    
    def __init__(self, client, channel_id: int, channel_name: str = "",
                 channel_passcode: int = 0,
                 recordings_dir: str = "recordings",
                 enable_audio_processing: bool = True,
                 headless: bool = True):
        """
        Args:
            client: 已登录的 BSHTClient 实例 (共享)
            channel_id: 频道 ID
            channel_name: 频道显示名 (用于文件名)
            channel_passcode: 频道密码
            recordings_dir: 录音存储根目录
            enable_audio_processing: 是否启用音频预处理 (高通滤波+AGC)
            headless: 无头模式 (True=不播放音频, 适合云服务器)
        """
        self.client = client
        self.channel_id = channel_id
        self.channel_name = channel_name or f"ch{channel_id}"
        self.channel_passcode = channel_passcode
        self.recordings_dir = recordings_dir
        self.enable_audio_processing = enable_audio_processing
        self.headless = headless
        
        self._logger = logging.getLogger(f"Worker.{self.channel_name}")
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        
        # 运行时组件 (在 _run 中初始化)
        self._listener = None
        self._recorder = None
        self._user_cache: Dict[int, str] = {}
        self._user_fetching = set()
        self._user_fetching_lock = threading.Lock()
        self._active_speakers: Dict[int, float] = {}
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    def start(self):
        """启动工作线程"""
        if self._is_running:
            self._logger.warning("已在运行中")
            return
        
        self._is_running = True
        self._thread = threading.Thread(
            target=self._run, 
            name=f"ChannelWorker-{self.channel_name}",
            daemon=True
        )
        self._thread.start()
        self._logger.info(f"频道工作线程已启动: {self.channel_name} ({self.channel_id})")
    
    def stop(self):
        """停止工作线程"""
        self._is_running = False
        if self._listener:
            self._listener.stop_listening()
        if self._recorder:
            self._recorder.close_all()
        if self._thread:
            self._thread.join(timeout=5)
        self._logger.info(f"频道工作线程已停止: {self.channel_name}")
    
    def _run(self):
        """主运行循环 (含自动重连)"""
        from bsht_client import AudioStreamListener, AudioFrame
        
        while self._is_running:
            try:
                # 1. 确保已加入频道
                if not self._ensure_joined():
                    self._logger.warning("无法加入频道，10秒后重试...")
                    self._sleep(10)
                    continue
                
                # 2. 创建独立的 listener
                self._listener = AudioStreamListener(self.client)
                self._setup_callbacks()
                
                # 3. 连接语音服务器
                conn = self._listener.connect(self.channel_id)
                if not conn.success:
                    self._logger.error(f"连接语音服务器失败: {conn.error}")
                    self._sleep(10)
                    continue
                
                self._logger.info(f"语音服务器连接成功: {conn.data['ip']}:{conn.data['port']}")
                
                # 4. 启动监听
                if not self._listener.start_listening():
                    self._logger.error("启动监听失败")
                    self._sleep(10)
                    continue
                
                self._logger.info("音频监听已启动")
                
                # 5. 预加载成员昵称
                self._preload_member_names()
                
                # 6. 设置录音器
                self._setup_recorder()
                
                # 7. 保活循环
                self._keep_alive_loop()
                
                # 退出保活 → 清理
                if self._recorder:
                    self._recorder.close_all()
                self._listener.stop_listening()
                self._logger.warning("保活循环结束")
                
            except Exception as e:
                self._logger.error(f"工作线程异常: {e}")
                import traceback
                self._logger.error(traceback.format_exc())
                if self._listener:
                    try:
                        self._listener.stop_listening()
                    except:
                        pass
            
            if self._is_running:
                self._logger.info("10秒后重连...")
                self._sleep(10)
    
    def _sleep(self, seconds: float):
        """可中断的 sleep"""
        end = time.time() + seconds
        while time.time() < end and self._is_running:
            time.sleep(0.5)
    
    def _ensure_joined(self) -> bool:
        """确保已加入频道"""
        try:
            # 检查是否已是成员
            channels = self.client.get_user_channels()
            if channels.success:
                for ch in channels.data:
                    if ch.channel_id == self.channel_id:
                        self._logger.info(f"已是频道成员: {ch.name} ({self.channel_id})")
                        if not self.channel_name or self.channel_name == f"ch{self.channel_id}":
                            self.channel_name = ch.name
                        return True
            
            # 尝试加入
            self._logger.info(f"尝试加入频道: {self.channel_id}")
            join = self.client.join_channel(self.channel_id, self.channel_passcode)
            if join.success:
                self._logger.info("加入频道成功")
                return True
            else:
                self._logger.error(f"加入频道失败: {join.error}")
                return False
                
        except Exception as e:
            self._logger.error(f"加入频道异常: {e}")
            return False
    
    def _setup_callbacks(self):
        """设置音频回调"""
        from bsht_client import AudioFrame
        
        def on_audio(frame: AudioFrame):
            current_time = time.time()
            try:
                if frame.user_id == 0:
                    return
                
                # 获取昵称
                name = self._user_cache.get(frame.user_id)
                if not name:
                    name = f"用户({frame.user_id})"
                    self._trigger_name_fetch(frame.user_id)
                
                # 停止说话
                if frame.is_stop:
                    if frame.user_id in self._active_speakers:
                        stop_name = self._user_cache.get(frame.user_id, f"用户({frame.user_id})")
                        self._logger.info(f"🔴 [{self.channel_name}] 停止说话: {stop_name}")
                        del self._active_speakers[frame.user_id]
                    return
                
                # 新说话者
                if frame.user_id not in self._active_speakers:
                    self._logger.info(f"🎤 [{self.channel_name}] 开始说话: {name} ({frame.user_id})")
                
                self._active_speakers[frame.user_id] = current_time
                
            except Exception as e:
                self._logger.error(f"处理音频失败: {e}")
        
        def on_error(msg: str):
            self._logger.error(f"监听器错误: {msg}")
        
        self._listener.set_callbacks(on_audio_frame=on_audio, on_error=on_error)
    
    def _trigger_name_fetch(self, user_id: int):
        """异步获取用户昵称"""
        with self._user_fetching_lock:
            if user_id in self._user_fetching:
                return
            self._user_fetching.add(user_id)
        
        def fetch():
            try:
                info = self.client.get_user_info(user_id)
                if info.success and info.data.nickname:
                    self._user_cache[user_id] = info.data.nickname
                else:
                    self._user_cache[user_id] = f"未知({user_id})"
            except Exception:
                self._user_cache[user_id] = f"用户({user_id})"
            finally:
                with self._user_fetching_lock:
                    self._user_fetching.discard(user_id)
                    
                # 同步到混音器
                if self._listener and hasattr(self._listener, '_mixer') and self._listener._mixer:
                    self._listener._mixer.set_user_names(self._user_cache)
        
        threading.Thread(target=fetch, daemon=True).start()
    
    def _preload_member_names(self):
        """预加载频道成员昵称"""
        def _do_preload():
            try:
                result = self.client.get_channel_members(self.channel_id)
                if not result.success:
                    self._logger.warning(f"获取频道成员失败: {result.error}")
                    return
                
                members = result.data.get('members', [])
                self._logger.info(f"频道 {self.channel_name} 有 {len(members)} 个成员，加载昵称...")
                
                loaded = 0
                for member in members:
                    uid = member.user_id
                    if uid in self._user_cache:
                        continue
                    try:
                        info = self.client.get_user_info(uid)
                        if info.success and info.data.nickname:
                            self._user_cache[uid] = info.data.nickname
                        else:
                            self._user_cache[uid] = f"用户({uid})"
                        loaded += 1
                    except Exception:
                        self._user_cache[uid] = f"用户({uid})"
                
                self._logger.info(f"昵称加载完成: {loaded} 个新用户")
                
                # 同步到混音器
                if self._listener and hasattr(self._listener, '_mixer') and self._listener._mixer:
                    self._listener._mixer.set_user_names(self._user_cache)
                    
            except Exception as e:
                self._logger.error(f"预加载昵称失败: {e}")
        
        threading.Thread(target=_do_preload, daemon=True).start()
    
    def _setup_recorder(self):
        """设置录音器"""
        from channel_recorder import ChannelRecorder
        from audio_processor import AudioProcessor
        
        # 创建音频预处理器
        processor = AudioProcessor(sample_rate=48000) if self.enable_audio_processing else None
        
        # 创建录音器
        self._recorder = ChannelRecorder(
            base_dir=self.recordings_dir,
            channel_id=self.channel_id,
            channel_name=self.channel_name,
            recorder_type="RX",
            audio_processor=processor,
        )
        
        # 等待混音器初始化并连接
        for _ in range(50):  # 最多等 2.5s
            if hasattr(self._listener, '_mixer') and self._listener._mixer:
                self._listener._mixer.set_recorder(self._recorder)
                self._logger.info(f"录音器已连接到混音器: {self.channel_name}")
                return
            time.sleep(0.05)
        
        self._logger.warning("混音器未就绪，录音器未能连接")
    
    def _keep_alive_loop(self):
        """保活循环"""
        last_heartbeat = time.time()
        
        while self._is_running:
            try:
                now = time.time()
                
                # 说话者超时清理
                expired = [
                    uid for uid, t in self._active_speakers.items()
                    if now - t > self.SPEAKER_TIMEOUT
                ]
                for uid in expired:
                    name = self._user_cache.get(uid, f"用户({uid})")
                    self._logger.info(f"🔴 [{self.channel_name}] 停止说话: {name}")
                    del self._active_speakers[uid]
                
                # 频道状态心跳
                if now - last_heartbeat >= self.HEARTBEAT_INTERVAL:
                    last_heartbeat = now
                    try:
                        status = self.client.get_channel_status(self.channel_id)
                        if status.success:
                            online = len(status.data.get('online_users', []))
                            self._logger.info(f"[{self.channel_name}] 在线: {online} 人")
                        else:
                            self._logger.warning(f"[{self.channel_name}] 状态获取失败: {status.error}")
                    except Exception as e:
                        self._logger.warning(f"心跳异常: {e}")
                        continue
                
                # 监听器状态检查
                if not self._listener._is_listening:
                    self._logger.warning("监听器已停止，触发重连")
                    return
                
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                self._is_running = False
                return
            except Exception as e:
                self._logger.error(f"保活循环异常: {e}")
                time.sleep(1)
