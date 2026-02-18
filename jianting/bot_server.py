import time
import sys
import logging
import threading
from bsht_client import BSHTClient, TokenInfo, StatusCode, ChannelConnectionParams

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_server.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Suppress noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logger = logging.getLogger("BSHTBox")

class BotServer:
    def __init__(self, username, password, target_channel_id, channel_passcode=0):
        self.username = username
        self.password = password
        self.target_channel_id = target_channel_id
        self.channel_passcode = channel_passcode
        self.client = BSHTClient(auto_refresh_token=True)
        self.is_running = False

    def start(self):
        """启动机器人"""
        self.is_running = True
        logger.info("正在启动 BSHT 机器人...")

        # 1. 尝试加载凭证或重新登录
        if not self._login():
            logger.error("无法登录，机器人停止")
            return

        # 2. 启动主循环
        self._main_loop()

    def stop(self):
        """停止机器人"""
        self.is_running = False
        self.client.close()
        logger.info("机器人已停止")

    def _login(self) -> bool:
        """处理登录逻辑"""
        # 尝试加载本地凭证
        if self.client.load_credentials():
            logger.info("已加载本地凭证")
            # 验证凭证有效性
            if self.client.load_profile().success:
                logger.info(f"凭证有效，用户: {self.client.profile.nickname} ({self.client.profile.user_id})")
                return True
            else:
                logger.warning("本地凭证已失效，尝试重新登录...")
        
        # 使用账号密码登录
        logger.info(f"正在使用账号登录: {self.username}...")
        result = self.client.login(self.username, self.password)
        
        if result.success:
            # 登录成功后，必须加载用户资料以填充 self.profile
            self.client.load_profile()
            
            if self.client.profile:
                logger.info(f"登录成功，用户: {self.client.profile.nickname} ({self.client.profile.user_id})")
            else:
                logger.info(f"登录成功 (无法获取资料)")
                
            self.client.save_credentials() # 保存凭证
            
            # 设置 Token 刷新回调
            self.client.set_token_refresh_callback(self._on_token_refreshed)
            return True
        else:
            logger.error(f"登录失败: {result.error}")
            return False

    def _on_token_refreshed(self, token_info: TokenInfo):
        """Token 刷新回调"""
        logger.info("Token 已自动刷新，正在保存新凭证...")
        self.client.save_credentials()

    def _main_loop(self):
        """主业务循环"""
        from bsht_client import AudioStreamListener, AudioFrame
        
        # 初始化监听器
        self.listener = AudioStreamListener(self.client)
        self.user_cache = {}        # {user_id: nickname}
        self.user_fetching = set()  # Set of user_ids currently being fetched
        self.user_fetching_lock = threading.Lock()  # 保护 user_fetching 的线程安全锁
        self.active_speakers = {}   # {user_id: last_frame_time} 支持多人同时说话
        self.last_audio_time = 0    # Last audio packet time

        # 音频回调
        def on_audio(frame: AudioFrame):
            current_time = time.time()
            self.last_audio_time = current_time

            try:
                if frame.user_id == 0:
                    return

                # Speaker Identification (Non-blocking)
                name = self.user_cache.get(frame.user_id)

                if not name:
                     name = f"用户({frame.user_id})"

                     # Trigger background fetch if not already fetching
                     with self.user_fetching_lock:
                         if frame.user_id not in self.user_fetching:
                             self.user_fetching.add(frame.user_id)
                             should_fetch = True
                         else:
                             should_fetch = False

                     if should_fetch:
                         def fetch_info(uid):
                             try:
                                 info = self.client.get_user_info(uid)
                                 if info.success and info.data.nickname:
                                     self.user_cache[uid] = info.data.nickname
                                 else:
                                     self.user_cache[uid] = f"未知({uid})"
                             except Exception as e:
                                 logger.error(f"获取用户信息失败 (uid={uid}): {e}")
                                 self.user_cache[uid] = f"错误({uid})"
                             finally:
                                 with self.user_fetching_lock:
                                     self.user_fetching.discard(uid)

                         t = threading.Thread(target=fetch_info, args=(frame.user_id,), daemon=True)
                         t.start()
                
                # 检测 RX_AUDIO_STOP (精确PTT松开)
                if frame.is_stop:
                    if frame.user_id in self.active_speakers:
                        stop_name = self.user_cache.get(frame.user_id, f"用户({frame.user_id})")
                        logger.info(f"🔴 停止说话: {stop_name}")
                        del self.active_speakers[frame.user_id]
                    return
                
                # 说话者检测: 仅在新说话者首次出现时打印日志
                if frame.user_id not in self.active_speakers:
                    # 新说话者 → 打印一次日志
                    if frame.end_marker:
                        prefix = "🟢 PTT按键"
                    else:
                        prefix = "🎤 开始说话"
                    logger.info(f"{prefix}: {name} ({frame.user_id})")
                
                # 更新时间戳 (无论新旧说话者)
                self.active_speakers[frame.user_id] = current_time

            except Exception as e:
                logger.error(f"处理音频失败: {e}")

        def on_listening_error(msg: str):
            logger.error(f"监听器错误: {msg}")

        self.listener.set_callbacks(on_audio_frame=on_audio, on_error=on_listening_error)

        while self.is_running:
            try:
                # 1. 检查是否在频道中 (优先从已加入列表中查找)
                logger.info("获取用户频道列表...")
                user_channels_result = self.client.get_user_channels()
                is_joined = False
                
                if user_channels_result.success:
                    for ch in user_channels_result.data:
                        if ch.channel_id == self.target_channel_id:
                            logger.info(f"已是频道成员: {ch.name} ({ch.channel_id})")
                            is_joined = True
                            break
                
                if not is_joined:
                    logger.info(f"未加入，尝试加入目标频道: {self.target_channel_id}")
                    join_result = self.client.join_channel(self.target_channel_id, self.channel_passcode)
                    if join_result.success:
                        logger.info("加入频道成功")
                        is_joined = True
                    else:
                        logger.error(f"加入频道失败: {join_result.error}")
                
                if is_joined:
                    # 2. 连接语音服务器
                    logger.info("正在连接语音服务器...")
                    conn_result = self.listener.connect(self.target_channel_id)
                    
                    if conn_result.success:
                        logger.info(f"语音服务器连接成功: {conn_result.data['ip']}:{conn_result.data['port']}")
                        
                        # 3. 启动监听 (包含 UDP 心跳)
                        if self.listener.start_listening():
                            logger.info("音频监听已启动 (UDP 心跳运行中)")
                            
                            # === 预加载频道成员昵称 ===
                            self._preload_member_names()
                            
                            # === 启动频道录制器 ===
                            self._setup_recorder()
                            
                            # 4. 进入保活循环
                            self._keep_alive_loop()
                            
                            # 退出保活循环 → 关闭录制
                            if hasattr(self, '_recorder') and self._recorder:
                                self._recorder.close_all()
                            if hasattr(self, '_tx_recorder') and self._tx_recorder:
                                self._tx_recorder.close_all()
                            
                            logger.warning("保活循环结束，停止监听...")
                            self.listener.stop_listening()
                        else:
                            logger.error("启动监听失败")
                    else:
                        logger.error(f"连接语音服务器失败: {conn_result.error}")
                
                # 如果失败，清理并重试
                if not is_joined:
                   logger.warning("无法进入目标频道")

            except Exception as e:
                logger.error(f"主循环发生异常: {e}")
                # 确保清理
                if hasattr(self, 'listener'):
                    self.listener.stop_listening()
            
            # 如果异常退出，等待一段时间重试
            if self.is_running:
                logger.info("10秒后重试连接...")
                time.sleep(10)

    def _setup_recorder(self, recording_callback=None):
        """启动频道录制器，连接到混音器
        
        Args:
            recording_callback: 录音完成回调函数
        """
        from channel_recorder import ChannelRecorder

        # 统一目录: recordings/ (会自动按日期创建子目录)
        # RX 录音器 (接收/监听录音)
        self._recorder = ChannelRecorder(
            base_dir="recordings",
            channel_id=self.target_channel_id,
            recorder_type="RX",
            on_recording_complete=recording_callback
        )

        # TX 录音器 (发射录音)
        self._tx_recorder = ChannelRecorder(
            base_dir="recordings",
            channel_id=self.target_channel_id,
            recorder_type="TX",
            on_recording_complete=recording_callback
        )

        # 等待混音器初始化 (它在 listen 线程中创建)
        import time
        for _ in range(50):  # 最多等 2.5 秒
            if hasattr(self.listener, '_mixer') and self.listener._mixer:
                self.listener._mixer.set_recorder(self._recorder)
                self.listener._mixer.set_tx_recorder(self._tx_recorder)
                logger.info("录制器已连接到混音器 (RX + TX)")
                return
            time.sleep(0.05)

        logger.warning("混音器未就绪，录制器未能连接")

    def _preload_member_names(self):
        """预加载频道成员昵称"""
        import threading
        
        def _do_preload():
            try:
                members_result = self.client.get_channel_members(self.target_channel_id)
                if not members_result.success:
                    logger.warning(f"获取频道成员失败: {members_result.error}")
                    return
                
                members = members_result.data.get('members', [])
                logger.info(f"频道有 {len(members)} 个成员，正在加载昵称...")
                
                loaded = 0
                for member in members:
                    uid = member.user_id
                    if uid in self.user_cache:
                        continue
                    try:
                        info = self.client.get_user_info(uid)
                        if info.success and info.data.nickname:
                            self.user_cache[uid] = info.data.nickname
                        else:
                            self.user_cache[uid] = f"用户({uid})"
                        loaded += 1
                    except Exception as e:
                        logger.warning(f"获取用户 {uid} 信息失败: {e}")
                        self.user_cache[uid] = f"用户({uid})"
                
                logger.info(f"昵称加载完成: {loaded} 个新用户")
                
                # 把昵称映射传给混音器
                if hasattr(self.listener, '_mixer') and self.listener._mixer:
                    self.listener._mixer.set_user_names(self.user_cache)
                    logger.info(f"昵称已同步到混音器 ({len(self.user_cache)} 个)")
                    
            except Exception as e:
                logger.error(f"预加载昵称失败: {e}")
        
        # 后台线程加载，不阻塞主线程
        t = threading.Thread(target=_do_preload, daemon=True)
        t.start()

    def _keep_alive_loop(self):
        """频道内保活循环 (包含 PTT Release 检测)"""
        last_heartbeat_time = time.time()
        
        # 启动键盘 PTT 监听 (仅首次启动，重连时复用)
        if not getattr(self, '_ptt_thread_started', False):
            self._ptt_thread_started = True
            self._start_ptt_keyboard()
        
        while self.is_running:
            try:
                current_time = time.time()
                
                # --- 1. 说话者超时清理 (使用 active_speakers 字典) ---
                expired_speakers = [
                    uid for uid, last_time in self.active_speakers.items()
                    if current_time - last_time > 0.5
                ]
                for uid in expired_speakers:
                    name = self.user_cache.get(uid, f"用户({uid})")
                    logger.info(f"🔴 停止说话: {name}")
                    del self.active_speakers[uid]

                # --- 2. Application Layer Heartbeat (GetChannelStatus) ---
                # Check every 30 seconds
                if current_time - last_heartbeat_time >= 30:
                    last_heartbeat_time = current_time
                    
                    status_result = self.client.get_channel_status(self.target_channel_id)
                    if status_result.success:
                        online_count = len(status_result.data.get('online_users', []))
                        logger.info(f"[状态监控] 频道在线: {online_count} 人")
                    else:
                        logger.warning(f"[状态监控] 获取状态失败: {status_result.error}")

                # --- 3. Listener Status Check ---
                if not self.listener._is_listening:
                    logger.warning("检测到监听器已停止，尝试重新初始化")
                    return

                time.sleep(0.1) # Short sleep for responsiveness
                
            except KeyboardInterrupt:
                self.is_running = False
                # 确保停止发射
                if self.listener.is_transmitting:
                    self.listener.stop_transmit()
                return
            except Exception as e:
                logger.error(f"保活循环异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(1)
                # 继续循环而不是 return，避免心跳中断导致断连

    def _start_ptt_keyboard(self):
        """启动键盘 PTT 监听线程 (使用 GetAsyncKeyState 直接检测物理按键状态)"""
        import threading

        def keyboard_ptt_loop():
            """
            PTT 检测 - 使用 Win32 GetAsyncKeyState

            核心思路:
            - GetAsyncKeyState(VK_SPACE) 直接查询空格键是否被物理按下
            - 不依赖键盘重复事件，彻底消除重复延迟导致的误判
            - 松开后 300ms 冷却期，防止残余缓冲事件触发幽灵PTT
            """
            try:
                import ctypes
                import msvcrt

                user32 = ctypes.windll.user32
                VK_SPACE = 0x20  # 空格键虚拟键码

                logger.info("🎙️ 键盘PTT已就绪: [空格]=按住说话, [Q]=退出")
                logger.info("[PTT] 使用 GetAsyncKeyState 物理按键检测")

                ptt_pressed = False
                cooldown_until = 0  # 冷却期结束时间戳

                while self.is_running:
                    # 消耗键盘输入缓冲区 (处理 Q 退出，同时清除残余空格事件)
                    while msvcrt.kbhit():
                        key = msvcrt.getch()
                        if key in (b'q', b'Q'):
                            logger.info("收到退出指令")
                            if ptt_pressed:
                                self.listener.stop_transmit()
                            self.is_running = False
                            return

                    current_time = time.time()

                    # GetAsyncKeyState: 返回值最高位 (0x8000) 为1表示当前物理按下
                    space_down = bool(user32.GetAsyncKeyState(VK_SPACE) & 0x8000)

                    if space_down and not ptt_pressed:
                        # 空格键被按下，且当前未在发射状态
                        if current_time > cooldown_until:
                            # 冷却期已过，允许触发 PTT
                            ptt_pressed = True
                            logger.info("🟢 PTT按下 (本机)")
                            self.listener.start_transmit()
                        # else: 还在冷却期内，忽略 (防止幽灵PTT)

                    elif not space_down and ptt_pressed:
                        # 空格键已松开，且当前在发射状态 → 停止发射
                        ptt_pressed = False
                        logger.info("🔴 PTT松开 (本机)")
                        self.listener.stop_transmit()
                        # 设置 300ms 冷却期，防止 stop_transmit 后残余事件触发新PTT
                        cooldown_until = time.time() + 0.3

                    time.sleep(0.010)  # 10ms 轮询

            except Exception as e:
                logger.error(f"键盘PTT异常: {e}")
                import traceback
                logger.error(traceback.format_exc())

        t = threading.Thread(target=keyboard_ptt_loop, daemon=True)
        t.start()


def create_recording_callback(recognizer, channel_id):
    """创建录音完成回调函数"""
    def callback(filepath: str, duration: float, user_id: str, user_name: str,
                 channel_id: int = 0, recorder_type: str = "RX"):
        recognizer.on_recording_complete(
            filepath=filepath,
            duration=duration,
            user_id=user_id,
            user_name=user_name,
            channel_id=channel_id,
            recorder_type=recorder_type
        )
    return callback


if __name__ == "__main__":
    # 配置
    USERNAME = "bswxd"
    PASSWORD = "BsWxd2026"
    CHANNEL_ID = 62793  # 目标频道ID
    CHANNEL_PASSCODE = 0 # 频道密码 (如果有)

    # 尝试加载环境变量配置
    import os
    try:
        from src.config import load_env_file, get_config
        load_env_file(".env")
        config = get_config()
        
        if config.dsp.enabled and config.api.siliconflow_key:
            # 创建识别器
            from src.recognizer import RecordingRecognizer
            recognizer = RecordingRecognizer(
                api_key=config.api.siliconflow_key,
                dsp_config={
                    "algorithm": config.dsp.algorithm,
                    "agc_mode": config.dsp.agc_mode,
                    "snr_threshold_high": config.dsp.snr_threshold_high,
                    "snr_threshold_low": config.dsp.snr_threshold_low
                }
            )
            
            # 设置数据库
            from src.database import get_database
            db = get_database(config.database.path)
            recognizer.set_database(db)
            
            # 创建回调函数
            recording_callback = create_recording_callback(recognizer, CHANNEL_ID)
            
            print("🎯 伪实时识别已启用")
            
            # 修改 BotServer 来使用回调
            original_setup = BotServer._setup_recorder
            
            def new_setup(self, callback=None):
                return original_setup(self, recording_callback)
            
            BotServer._setup_recorder = new_setup
            
            print("✅ 识别器已集成到 bot_server")
        else:
            print("⚠️  DSP未启用或API Key未配置，只录制不识别")
            recording_callback = None
    except Exception as e:
        print(f"⚠️  识别器初始化失败: {e}")
        recording_callback = None

    bot = BotServer(USERNAME, PASSWORD, CHANNEL_ID, CHANNEL_PASSCODE)
    try:
        bot.start()
    except KeyboardInterrupt:
        bot.stop()
