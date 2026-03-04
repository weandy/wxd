import time
import sys
import os
import asyncio
import logging
import threading
from bsht_client import BSHTClient, TokenInfo, StatusCode, ChannelConnectionParams, AudioStreamListener
from pathlib import Path


def get_reconnect_delay(attempt: int, base: int = 2, max_delay: int = 60, min_delay: int = 2) -> int:
    """计算指数退避延迟时间

    Args:
        attempt: 重试次数（从0开始）
        base: 指数基数（默认2，即 2, 4, 8, 16...）
        max_delay: 最大延迟秒数（默认60秒）
        min_delay: 最小延迟秒数（默认2秒）

    Returns:
        延迟秒数
    """
    delay = min(max_delay, base ** attempt)
    return max(min_delay, delay)

# 共享状态模块 (纯 Bot 模式不需要 Web 广播)
def get_bot_state():
    return None

def broadcast_bot_status(*args, **kwargs):
    pass

def broadcast_channel_update(*args, **kwargs):
    pass

def broadcast_speaking(*args, **kwargs):
    pass

def broadcast_recording(*args, **kwargs):
    pass


def interactive_select_channel(username: str, password: str) -> int:
    """交互式选择频道
    
    Args:
        username: BSHT用户名
        password: BSHT密码
        
    Returns:
        选择的频道ID
    """
    print("\n" + "=" * 50)
    print("📡 交互式频道选择")
    print("=" * 50)
    
    # 创建客户端并登录
    client = BSHTClient(auto_refresh_token=True)
    
    print(f"\n[1] 登录账号: {username}")
    login_result = client.login(username, password)
    if not login_result.success:
        print(f"  ❌ 登录失败: {login_result.message}")
        return 0
    
    print(f"  ✓ 登录成功")
    
    # 获取用户加入的频道
    print(f"\n[2] 获取加入的频道...")
    channels_resp = client.get_user_channels(offset=0, limit=20)
    if not channels_resp.success or not channels_resp.data:
        print(f"  ❌ 获取频道失败或没有加入任何频道: {channels_resp.error}")
        return 0
    
    channels = channels_resp.data
    print(f"  ✓ 已加入 {len(channels)} 个频道")
    
    # 显示频道列表
    print("\n📋 请选择要加入的频道:")
    print("-" * 40)
    for i, ch in enumerate(channels):
        admin_tag = " [管理员]" if ch.is_admin else ""
        banned_tag = " [已封禁]" if ch.is_banned else ""
        print(f"  [{i + 1}] {ch.name} (ID: {ch.channel_id}){admin_tag}{banned_tag}")
    print("-" * 40)
    
    # 让用户选择
    while True:
        try:
            choice = input("\n👉 请输入频道编号 (1-{len(channels)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(channels):
                selected = channels[idx]
                if selected.is_banned:
                    print("  ⚠️ 该频道已被封禁，无法加入")
                    continue
                print(f"\n  ✓ 已选择: {selected.name} (ID: {selected.channel_id})")
                
                # 询问是否保存到.env
                save = input("  💾 是否保存到 .env 文件? (y/n): ").strip().lower()
                if save == 'y' or save == 'yes':
                    # 读取现有.env
                    env_path = ".env"
                    env_vars = {}
                    if os.path.exists(env_path):
                        with open(env_path, 'r', encoding='utf-8') as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith('#') and '=' in line:
                                    key, val = line.split('=', 1)
                                    env_vars[key.strip()] = val.strip().strip('"').strip("'")
                    
                    # 更新频道ID
                    env_vars['BSHT_CHANNEL_ID'] = str(selected.channel_id)
                    
                    # 写回.env
                    with open(env_path, 'w', encoding='utf-8') as f:
                        f.write("# BSHT账号配置(前往客户端注册并且加入channel)\n")
                        for key, val in env_vars.items():
                            f.write(f"{key}={val}\n")
                    
                    print(f"  ✓ 已保存到 .env: BSHT_CHANNEL_ID={selected.channel_id}")
                
                return selected.channel_id
            else:
                print(f"  ❌ 请输入 1-{len(channels)} 之间的数字")
        except ValueError:
            print("  ❌ 请输入有效的数字")


class BotServer:
    pass


# 使用新的日志配置
from src.logging_setup import setup_logger, LOGS_DIR
import sys

logger = setup_logger("BSHTBox", "main")

# 静默第三方库日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)

# 打印启动信息
print(f"\n📁 日志目录: {LOGS_DIR}")
print(f"📝 日志文件: logs/bot_server.log (按天轮转, 保留7天)")
print(f"📝 识别日志: logs/recognize.log")
print(f"📝 错误日志: logs/error.log\n")

# 导入异步优化模块
import time
import threading
from async_optimization import get_metrics_collector, get_thread_pool, timed_sync

class BotServer:
    def __init__(self, username, password, target_channel_id, channel_passcode=0,
                 enable_console_ptt=False, enable_playback=False):
        self.username = username
        self.password = password
        self.target_channel_id = target_channel_id
        self.channel_passcode = channel_passcode
        self.enable_console_ptt = enable_console_ptt
        self.enable_playback = enable_playback  # 是否启用音频播放
        self.client = BSHTClient(auto_refresh_token=True)
        self.is_running = False

        # 初始化异步优化组件
        self.metrics = get_metrics_collector()
        self.thread_pool = get_thread_pool()

        # 加载 TTS 配置
        try:
            from src.config import get_config
            config = get_config()
            self.tts_worker_url = config.tts.worker_url
            self.tts_default_voice = config.tts.default_voice
            self.tts_default_speed = config.tts.default_speed
            logger.info(f"✅ TTS配置加载成功: {self.tts_worker_url}")
        except Exception as e:
            logger.warning(f"⚠️ TTS配置加载失败: {e}，使用默认配置")
            self.tts_worker_url = "https://tts.cnleestar.workers.dev"
            self.tts_default_voice = "zh-CN-YunxiNeural"
            self.tts_default_speed = 1.0

        # ========== 连接健康监控参数 ==========
        self._last_packet_time = 0          # 最后收到数据包时间
        self._unhealthy_count = 0           # 连续不健康计数
        self._unhealthy_threshold = 10      # 触发重连的不健康次数阈值
        self._packet_timeout = 0           # 数据包超时时间(秒) - 0=禁用数据包超时检测
        self._health_check_interval = 30    # 健康检查间隔(秒) - 增加到30秒
        self._is_reconnecting = False       # 是否正在重连中
        self._enable_packet_timeout = False # 是否启用数据包超时检测（针对静默频道）

        # 启动性能监控线程
        self._start_metrics_monitor()

        # 启动健康检查线程
        self._start_health_check()

        # 启动 API 服务器
        self._start_api_server()

        logger.info(f"异步优化组件已初始化 (console_ptt={'开启' if enable_console_ptt else '关闭'})")

    def _start_metrics_monitor(self):
        """启动性能监控线程 (每60秒报告一次)"""
        def monitor():
            while self.is_running:
                time.sleep(60)
                self._print_metrics_summary()

        self._monitor_thread = threading.Thread(target=monitor, daemon=True)
        self._monitor_thread.start()

    def _start_health_check(self):
        """启动连接健康检查线程 (每10秒检查一次)"""
        def health_check():
            while self.is_running:
                time.sleep(self._health_check_interval)
                self._check_connection_health()

        self._health_check_thread = threading.Thread(target=health_check, daemon=True, name="HealthCheck")
        self._health_check_thread.start()
        logger.info("✅ 连接健康检查线程已启动")

    def _start_api_server(self):
        """启动 HTTP API 服务器（在单独线程中）"""
        def run_api_server():
            try:
                from flask import Flask, request, jsonify
                from flask_cors import CORS

                logger.info("[Flask] 正在创建 Flask 应用...")
                app = Flask(__name__)
                CORS(app)  # 允许跨域请求
                logger.info("[Flask] CORS 已启用")

                @app.route('/api/broadcast/audio', methods=['POST'])
                def broadcast_audio():
                    """接收音频广播请求"""
                    try:
                        data = request.get_json()
                        audio_path = data.get('audio_path')
                        channel_id = data.get('channel_id', self.target_channel_id)

                        if not audio_path:
                            return jsonify({
                                'success': False,
                                'message': '缺少 audio_path 参数'
                            }), 400

                        # 检查文件是否存在
                        if not Path(audio_path).exists():
                            return jsonify({
                                'success': False,
                                'message': f'音频文件不存在: {audio_path}'
                            }), 404

                        # 检查频道是否匹配
                        if channel_id != self.target_channel_id:
                            logger.warning(f"[API] 广播频道不匹配: 请求={channel_id}, 当前={self.target_channel_id}")

                        logger.info(f"[API] 收到音频广播请求: {audio_path}")

                        # 在单独线程中播放音频，避免阻塞 API 响应
                        def play_audio_async():
                            try:
                                self._play_audio_file(audio_path)
                                logger.info(f"[API] 音频广播完成: {audio_path}")
                            except Exception as e:
                                logger.error(f"[API] 音频广播失败: {e}")

                        threading.Thread(target=play_audio_async, daemon=True).start()

                        return jsonify({
                            'success': True,
                            'message': '音频广播已开始',
                            'audio_path': audio_path,
                            'channel_id': channel_id
                        })

                    except Exception as e:
                        logger.error(f"[API] 处理广播请求失败: {e}")
                        return jsonify({
                            'success': False,
                            'message': f'服务器错误: {str(e)}'
                        }), 500

                @app.route('/api/broadcast/tts', methods=['POST'])
                def broadcast_tts():
                    """接收 TTS 广播请求"""
                    import tempfile
                    import os
                    try:
                        data = request.get_json()
                        text = data.get('text')
                        channel_id = data.get('channel_id', self.target_channel_id)
                        voice = data.get('voice', 'zh-CN-XiaoxiaoNeural')

                        if not text:
                            return jsonify({
                                'success': False,
                                'message': '缺少 text 参数'
                            }), 400

                        logger.info(f"[API] 收到 TTS 广播请求: {text[:50]}...")

                        # 使用 TTS 生成语音（优先 edge-tts 备用方案）
                        def generate_and_play():
                            try:
                                import subprocess

                                # 创建 tts 目录
                                tts_dir = Path("tts")
                                tts_dir.mkdir(exist_ok=True)

                                # 生成文件名
                                timestamp = time.strftime("%Y%m%d_%H%M%S")
                                mp3_file = tts_dir / f"{timestamp}.mp3"
                                wav_file = tts_dir / f"{timestamp}.wav"

                                # 方案1: 尝试使用 TTS Worker API
                                try:
                                    import requests

                                    logger.info(f"[API] 尝试使用 TTS Worker API: {voice}")

                                    tts_url = f"{self.tts_worker_url}/v1/audio/speech"
                                    payload = {
                                        "input": text,
                                        "voice": voice,
                                        "speed": self.tts_default_speed,
                                        "pitch": "0",
                                        "style": "general"
                                    }

                                    response = requests.post(tts_url, json=payload, timeout=30)

                                    if response.status_code == 200 and len(response.content) > 0:
                                        with open(mp3_file, 'wb') as f:
                                            f.write(response.content)
                                        logger.info(f"[API] TTS Worker API 成功: {mp3_file}")
                                    else:
                                        raise Exception(f"TTS Worker API 返回空内容 (status={response.status_code})")

                                except Exception as api_error:
                                    logger.warning(f"[API] TTS Worker API 失败: {api_error}")
                                    logger.info(f"[API] 使用 edge-tts 作为备用方案")

                                    # 方案2: 使用 edge-tts (备用)
                                    async def generate_with_edge():
                                        import edge_tts
                                        communicate = edge_tts.Communicate(text, voice)
                                        await communicate.save(str(mp3_file))

                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        loop.run_until_complete(generate_with_edge())
                                    finally:
                                        loop.close()

                                    logger.info(f"[API] edge-tts 生成成功: {mp3_file}")

                                # 使用 ffmpeg 转换为 WAV
                                try:
                                    subprocess.run([
                                        'ffmpeg', '-y', '-i', str(mp3_file),
                                        '-ar', '16000',  # 采样率 16kHz
                                        '-ac', '1',      # 单声道
                                        '-acodec', 'pcm_s16le',  # 16-bit PCM
                                        str(wav_file)
                                    ], check=True, capture_output=True)

                                    logger.info(f"[API] TTS WAV 已转换: {wav_file}")

                                    # 播放 WAV 文件
                                    self._play_audio_file(str(wav_file))

                                    logger.info(f"[API] TTS 广播完成")

                                    return True
                                except subprocess.CalledProcessError as e:
                                    logger.error(f"[API] ffmpeg 转换失败: {e}")
                                    logger.error(f"[API] stderr: {e.stderr.decode() if e.stderr else 'N/A'}")
                                    return False
                                except FileNotFoundError:
                                    logger.error(f"[API] ffmpeg 未找到，请安装 ffmpeg")
                                    return False

                            except Exception as e:
                                logger.error(f"[API] TTS 生成或播放失败: {e}")
                                return False

                        # 在单独线程中执行（同步任务）
                        threading.Thread(target=generate_and_play, daemon=True).start()

                        return jsonify({
                            'success': True,
                            'message': 'TTS 广播已开始',
                            'text': text
                        })

                    except Exception as e:
                        logger.error(f"[API] 处理 TTS 请求失败: {e}")
                        return jsonify({
                            'success': False,
                            'message': f'服务器错误: {str(e)}'
                        }), 500

                @app.route('/api/status', methods=['GET'])
                def get_status():
                    """获取 Bot 状态"""
                    return jsonify({
                        'running': self.is_running,
                        'channel_id': self.target_channel_id,
                        'has_listener': hasattr(self, 'listener') and self.listener is not None
                    })

                # 启动 Flask 服务器
                logger.info("🌐 Bot API 服务器启动中...")
                logger.info("[Flask] 监听地址: http://127.0.0.1:8765")
                app.run(host='127.0.0.1', port=8765, debug=False, use_reloader=False)
            except ImportError as e:
                logger.error(f"[Flask] 导入错误: {e}")
                logger.warning("Flask 未安装，Bot API 服务器无法启动")
                logger.warning("请运行: pip install flask flask-cors")
            except Exception as e:
                logger.error(f"[Flask] 启动失败: {e}")
                import traceback
                logger.error(traceback.format_exc())

        logger.info("[API] 创建 API 服务器线程...")
        self._api_thread = threading.Thread(target=run_api_server, daemon=False, name="BotAPI")
        self._api_thread.start()
        logger.info("✅ Bot API 服务器线程已启动 (http://127.0.0.1:8765)")

        # 等待一下确保 Flask 启动
        time.sleep(0.5)
        if self._api_thread.is_alive():
            logger.info("✅ Bot API 服务器线程运行中")
        else:
            logger.warning("⚠️ Bot API 服务器线程已退出")


    def _check_connection_health(self):
        """
        检查连接健康状态

        检查项:
        1. 监听器是否运行
        2. 是否收到数据包（可选，针对活跃频道）
        3. API 调用是否成功

        对于静默频道（24小时无人说话）：
        - 禁用数据包超时检测
        - 只依赖监听器状态和 API 调用
        """
        # 如果正在重连，跳过检查
        if self._is_reconnecting:
            return

        # 检查监听器状态
        if not hasattr(self, 'listener') or not self.listener:
            return

        if not self.listener.is_listening:
            logger.error("❌ 监听器未运行，尝试重启...")
            self._restart_listener()
            return

        # === 数据包接收检查（仅针对活跃频道） ===
        # 对于长时间静默的频道，应该禁用此项检查
        if self._enable_packet_timeout and self._last_packet_time > 0:
            idle_time = time.time() - self._last_packet_time

            if idle_time > self._packet_timeout:
                self._unhealthy_count += 1
                logger.warning(
                    f"⚠️ 连接不健康 ({idle_time:.0f}秒无包, "
                    f"连续不健康 {self._unhealthy_count}/{self._unhealthy_threshold})"
                )

                if self._unhealthy_count >= self._unhealthy_threshold:
                    logger.error("❌ 连接持续不健康，尝试重新连接频道...")
                    logger.error(f"   最后收到数据包: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._last_packet_time))}")
                    self._reconnect_channel()
            else:
                # 连接正常，重置计数器
                if self._unhealthy_count > 0:
                    logger.info(f"✅ 连接恢复正常 (闲置 {idle_time:.0f}秒)")
                    self._unhealthy_count = 0

        # === 数据包超时检测禁用时，定期记录状态 ===
        elif not self._enable_packet_timeout:
            if self._last_packet_time > 0:
                idle_time = time.time() - self._last_packet_time

                if idle_time > 3600:  # 每小时记录一次
                    hours = int(idle_time // 3600)
                    minutes = int((idle_time % 3600) // 60)

                    if hours > 0:
                        time_str = f"{hours}小时{minutes}分钟"
                    else:
                        time_str = f"{minutes}分钟"

                    logger.info(f"📊 频道静默中 (距上次说话: {time_str})")
                    self._last_packet_time = time.time()  # 重置计时器，避免每小时都记录

    def _restart_listener(self):
        """重启监听器"""
        if self._is_reconnecting:
            logger.debug("正在重连中，跳过监听器重启")
            return False

        self._is_reconnecting = True

        try:
            # 停止旧监听器
            if hasattr(self, 'listener') and self.listener:
                logger.info("停止旧监听器...")
                self.listener.stop_listening()

            # 重新启动监听器
            logger.info("重新启动监听器...")
            self.listener = AudioStreamListener(self.client, enable_playback=self.enable_playback)

            # 连接到频道
            connect_result = self.listener.connect(self.target_channel_id)
            if not connect_result.success:
                logger.error(f"连接语音服务器失败: {connect_result.error}")
                return False

            # 设置回调
            self._setup_listener_callbacks()

            # 启动监听
            if not self.listener.start_listening():
                logger.error("启动监听失败")
                return False

            # 重置状态
            self._last_packet_time = time.time()
            self._unhealthy_count = 0
            self._is_reconnecting = False

            logger.info("✅ 监听器重启成功")
            return True

        except Exception as e:
            logger.error(f"❌ 监听器重启失败: {e}")
            self._is_reconnecting = False
            return False

    def _reconnect_channel(self):
        """重新连接频道"""
        if self._is_reconnecting:
            logger.debug("正在重连中，跳过频道重连")
            return

        self._is_reconnecting = True
        self._unhealthy_count = 0  # 重置计数器

        logger.info("🔄 开始重新连接频道...")

        try:
            # 1. 停止监听
            if hasattr(self, 'listener') and self.listener:
                self.listener.stop_listening()

            # 2. 重新加入频道
            logger.info(f"重新加入频道 {self.target_channel_id}...")
            join_result = self.client.join_channel(
                self.target_channel_id,
                self.channel_passcode
            )

            if not join_result.success:
                logger.error(f"重新加入频道失败: {join_result.error}")

                # 尝试完整重连 (退出后重新加入)
                logger.info("尝试完整重连流程...")
                quit_result = self.client.quit_channel(self.target_channel_id)
                logger.info(f"退出频道: {'成功' if quit_result.success else quit_result.error}")

                # 重新加入
                join_result = self.client.join_channel(
                    self.target_channel_id,
                    self.channel_passcode
                )

                if not join_result.success:
                    logger.error(f"完整重连失败: {join_result.error}")
                    self._is_reconnecting = False
                    return

            # 3. 重新启动监听
            self.listener = AudioStreamListener(self.client, enable_playback=self.enable_playback)
            connect_result = self.listener.connect(self.target_channel_id)

            if not connect_result.success:
                logger.error(f"重连语音服务器失败: {connect_result.error}")
                self._is_reconnecting = False
                return

            # 设置回调
            self._setup_listener_callbacks()

            # 启动监听
            if not self.listener.start_listening():
                logger.error("重新启动监听失败")
                self._is_reconnecting = False
                return

            # 重置状态
            self._last_packet_time = time.time()
            self._unhealthy_count = 0
            self._is_reconnecting = False

            logger.info("✅ 频道重连成功")

        except Exception as e:
            logger.error(f"❌ 频道重连失败: {e}")
            self._is_reconnecting = False

    def _print_metrics_summary(self):
        """打印性能指标摘要"""
        logger.info("=" * 40)
        logger.info("📊 性能指标报告")
        logger.info("=" * 40)

        for m in self.metrics.get_all_metrics():
            if m.count > 0:
                logger.info(f"{m.operation}: "
                          f"次数={m.count}, "
                          f"平均={m.avg_time*1000:.1f}ms, "
                          f"最大={m.max_time*1000:.1f}ms, "
                          f"错误={m.errors}({m.error_rate*100:.1f}%)")

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
        """停止机器人并清理所有资源"""
        self.is_running = False

        self.client.close()
        logger.info("机器人已停止")

        # 清理混音器资源
        if hasattr(self, '_mixer') and self._mixer:
            try:
                self._mixer.shutdown()
            except Exception as e:
                logger.warning(f"清理混音器失败: {e}")

        # 清理录制器
        if hasattr(self, '_recorder') and self._recorder:
            try:
                self._recorder.close_all()
            except Exception as e:
                logger.warning(f"清理录制器失败: {e}")

        if hasattr(self, '_tx_recorder') and self._tx_recorder:
            try:
                self._tx_recorder.close_all()
            except Exception as e:
                logger.warning(f"清理TX录制器失败: {e}")

        logger.info("所有资源已清理")

    @timed_sync("bot_server.login")
    def _login(self) -> bool:
        """处理登录逻辑 (带性能计时)"""
        start_time = time.time()
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

    @timed_sync("bot_server.token_refresh")
    def _on_token_refreshed(self, token_info: TokenInfo):
        """Token 刷新回调"""
        logger.info("Token 已自动刷新，正在保存新凭证...")
        self.client.save_credentials()

    def _main_loop(self):
        """主业务循环"""
        from bsht_client import AudioStreamListener, AudioFrame

        # 初始化监听器
        self.listener = AudioStreamListener(self.client, enable_playback=self.enable_playback)
        self.listener.enable_local_mic = self.enable_console_ptt  # 仅控制台 PTT 需要本地麦克风
        self.user_cache = {}        # {user_id: nickname}
        self.user_fetching = set()  # Set of user_ids currently being fetched
        self.user_fetching_lock = threading.Lock()  # 保护 user_fetching 的线程安全锁
        self.active_speakers = {}   # {user_id: last_frame_time} 支持多人同时说话
        self.last_audio_time = 0    # Last audio packet time

        # 音频回调
        def on_audio(frame: AudioFrame):
            current_time = time.time()
            self.last_audio_time = current_time
            # 更新健康监控的最后包时间
            self._last_packet_time = current_time

            try:
                if frame.user_id == 0:
                    return

                # 记录语音活跃度 (VOX Monitor)
                try:
                    from src.activity_monitor import monitor
                    if hasattr(self, 'status') and self.status.get('channel_id'):
                        monitor.record_activity(self.status['channel_id'], frame.user_id)
                except Exception as e:
                    logger.debug(f"VOX Monitor 记录失败: {e}")

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
                        # 广播停止说话状态
                        broadcast_speaking(str(frame.user_id), stop_name, False)
                    return

                # 说话者检测: 仅在新说话者首次出现时打印日志
                if frame.user_id not in self.active_speakers:
                    # 新说话者 → 打印一次日志
                    if frame.end_marker:
                        prefix = "🟢 PTT按键"
                    else:
                        prefix = "🎤 开始说话"
                    logger.info(f"{prefix}: {name} ({frame.user_id})")
                    # 广播开始说话状态
                    broadcast_speaking(str(frame.user_id), name, True)
                
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
                start = time.time()
                user_channels_result = self.client.get_user_channels()
                self.metrics.record("api.get_user_channels", time.time() - start)
                is_joined = False
                
                if user_channels_result.success:
                    for ch in user_channels_result.data:
                        if ch.channel_id == self.target_channel_id:
                            logger.info(f"已是频道成员: {ch.name} ({ch.channel_id})")
                            is_joined = True
                            break
                
                if not is_joined:
                    logger.info(f"未加入，尝试加入目标频道: {self.target_channel_id}")
                    start = time.time()
                    join_result = self.client.join_channel(self.target_channel_id, self.channel_passcode)
                    self.metrics.record("api.join_channel", time.time() - start)
                    if join_result.success:
                        logger.info("加入频道成功")
                        is_joined = True
                    else:
                        logger.error(f"加入频道失败: {join_result.error}")
                
                if is_joined:
                    # 2. 连接语音服务器
                    logger.info("正在连接语音服务器...")
                    start = time.time()
                    conn_result = self.listener.connect(self.target_channel_id)
                    self.metrics.record("audio.connect", time.time() - start)

                    if conn_result.success:
                        logger.info(f"语音服务器连接成功: {conn_result.data['ip']}:{conn_result.data['port']}")

                        # 获取频道状态（在线人数）
                        start = time.time()
                        status_result = self.client.get_channel_status(self.target_channel_id)
                        self.metrics.record("api.get_channel_status", time.time() - start)
                        initial_online_count = 0
                        if status_result.success:
                            initial_online_count = len(status_result.data.get('online_users', []))
                            logger.info(f"频道在线: {initial_online_count} 人")

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
            
            # 如果异常退出，等待一段时间重试（指数退避）
            if self.is_running:
                reconnect_attempt = getattr(self, '_reconnect_attempt', 0)
                delay = get_reconnect_delay(reconnect_attempt)
                logger.info(f"{delay}秒后重试连接... (尝试 {reconnect_attempt + 1})")
                time.sleep(delay)
                self._reconnect_attempt = reconnect_attempt + 1

    @timed_sync("bot_server.setup_recorder")
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

    @timed_sync("bot_server.preload_members")
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

    @timed_sync("bot_server.keep_alive_loop")
    def _keep_alive_loop(self):
        """频道内保活循环 (包含 PTT Release 检测 + 命令轮询)"""
        last_heartbeat_time = time.time()
        last_cmd_poll_time = 0  # 命令轮询计时器
        
        # 启动键盘 PTT 监听 (仅 enable_console_ptt=True 时启用)
        if self.enable_console_ptt and not getattr(self, '_ptt_thread_started', False):
            self._ptt_thread_started = True
            self._start_ptt_keyboard()
        elif not self.enable_console_ptt:
            logger.info("控制台 PTT 已禁用，使用 Web 端 PTT")
        
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
                    # 广播停止说话状态
                    broadcast_speaking(str(uid), name, False)

                # --- 2. Application Layer Heartbeat (GetChannelStatus) ---
                # 每30秒检查一次，这是判断连接是否正常的可靠方式
                # 对于长时间静默的频道，只能依赖 API 调用，无法通过数据包判断
                if current_time - last_heartbeat_time >= 30:
                    last_heartbeat_time = current_time

                    start = time.time()
                    status_result = self.client.get_channel_status(self.target_channel_id)
                    self.metrics.record("api.get_channel_status", time.time() - start)

                    if status_result.success:
                        online_count = len(status_result.data.get('online_users', []))

                        # 计算距离上次说话的时间
                        if self._last_packet_time > 0:
                            idle_time = time.time() - self._last_packet_time

                            # 格式化时间显示
                            if idle_time >= 3600:  # 超过1小时
                                hours = int(idle_time // 3600)
                                minutes = int((idle_time % 3600) // 60)
                                if hours > 0:
                                    idle_str = f"{hours}小时{minutes}分钟"
                                else:
                                    idle_str = f"{minutes}分钟"
                                logger.info(f"[状态监控] 频道在线: {online_count} 人 | 距上次说话: {idle_str}")
                            elif idle_time >= 60:  # 超过1分钟
                                minutes = int(idle_time // 60)
                                seconds = int(idle_time % 60)
                                idle_str = f"{minutes}分{seconds}秒" if seconds > 0 else f"{minutes}分钟"
                                logger.info(f"[状态监控] 频道在线: {online_count} 人 | 距上次说话: {idle_str}")
                            else:  # 少于1分钟
                                seconds = int(idle_time)
                                logger.info(f"[状态监控] 频道在线: {online_count} 人 | 距上次说话: {seconds}秒")
                        else:
                            # 从未收到过音频包
                            logger.info(f"[状态监控] 频道在线: {online_count} 人 | 暂无音频数据")
                    else:
                        # API 调用失败，可能是连接问题
                        self._unhealthy_count += 1
                        logger.warning(f"[状态监控] ⚠️ API 调用失败: {status_result.error} (连续失败 {self._unhealthy_count}/{self._unhealthy_threshold})")

                        # 连续 API 失败说明 gRPC 连接有问题
                        if self._unhealthy_count >= self._unhealthy_threshold:
                            logger.error("[状态监控] ❌ API 连续失败，gRPC 连接已断开，尝试重连...")
                            self.listener.stop_listening()  # 触发重连
                        else:
                            logger.info(f"[状态监控] API 失败，等待下次检查... ({self._unhealthy_count}/{self._unhealthy_threshold})")

                # --- 3. Listener Status Check & Reconnect ---
                if not self.listener._is_listening:
                    logger.warning("检测到监听器已停止，尝试重新连接...")
                    
                    # 重连参数
                    max_reconnects = 10
                    reconnect_count = 0
                    reconnected = False
                    
                    while reconnect_count < max_reconnects and self.is_running:
                        try:
                            # 停止现有监听器
                            self.listener.stop_listening()
                            
                            # 等待一小段时间
                            time.sleep(2)
                            
                            # 重新连接
                            start = time.time()
                            conn_result = self.listener.connect(self.target_channel_id)
                            self.metrics.record("audio.reconnect", time.time() - start)
                            if conn_result.success:
                                if self.listener.start_listening():
                                    logger.info(f"✅ 重新连接成功 (尝试 {reconnect_count + 1})")
                                    reconnected = True
                                    break
                            
                            reconnect_count += 1
                            wait_time = min(30, 2 ** reconnect_count)  # 指数退避，最多30秒
                            logger.warning(f"重连失败，{wait_time}s后重试 ({reconnect_count}/{max_reconnects})")
                            time.sleep(wait_time)
                            
                        except Exception as e:
                            reconnect_count += 1
                            delay = get_reconnect_delay(reconnect_count, max_delay=30)
                            logger.error(f"重连异常: {e}, {delay}秒后重试")
                            time.sleep(delay)
                    
                    if not reconnected:
                        logger.error("重连次数超限，退出")
                        break
                    
                    # 重新连接成功后，重新设置录制器
                    if reconnected:
                        try:
                            self._setup_recorder()
                        except Exception as e:
                            logger.error(f"重新设置录制器失败: {e}")

                # --- 4. 命令轮询 (每秒一次) ---
                if current_time - last_cmd_poll_time >= 1.0:
                    last_cmd_poll_time = current_time
                    self._process_pending_commands()

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

    def _process_pending_commands(self):
        """轮询并执行待处理的 Web 端指令"""
        try:
            # 检查 web 模块是否可用
            try:
                from web.models.database import poll_pending_commands, update_command_status
            except ImportError:
                # Web 模块不可用，跳过命令轮询
                return

            # 使用 Web 端数据库路径
            db_path = os.path.join('data', 'records.db')
            if not os.path.exists(db_path):
                return

            commands = poll_pending_commands(db_path)

            for cmd in commands:
                cmd_id = cmd['id']
                command = cmd['command']
                params = cmd.get('params')
                try:
                    result = self._execute_command(command, params)
                    update_command_status(cmd_id, 'done', result, db_path)
                except Exception as e:
                    logger.error(f"执行命令 {command} (id={cmd_id}) 失败: {e}")
                    update_command_status(cmd_id, 'error', str(e), db_path)

        except Exception as e:
            # 静默处理数据库不存在等情况
            if 'no such table' not in str(e):
                logger.error(f"命令轮询异常: {e}")

    def _execute_command(self, command: str, params: str = None) -> str:
        """执行单条命令，返回结果描述"""
        import json as _json

        if command == 'restart':
            logger.info("[CMD] 收到重启指令")
            # 在新线程中重启，避免阻塞轮询
            def do_restart():
                self.stop()
                time.sleep(2)
                self.start()
            threading.Thread(target=do_restart, daemon=True).start()
            return '重启已触发'

        elif command == 'ptt_start':
            logger.info("[CMD] 收到 Web PTT 开始指令")
            if hasattr(self, 'listener') and self.listener:
                self.listener.start_transmit()
                self._last_packet_time = time.time()  # 更新最后音频时间 (TX)
                return 'PTT 已开始'
            return 'listener 未就绪'

        elif command == 'ptt_stop':
            logger.info("[CMD] 收到 Web PTT 停止指令")
            if hasattr(self, 'listener') and self.listener:
                self.listener.stop_transmit()
                return 'PTT 已停止'
            return 'listener 未就绪'

        elif command == 'ptt_audio':
            # PCM 帧通过共享目录传递，由单独方法处理
            self._handle_ptt_audio_files()
            return 'ok'

        elif command == 'play_audio':
            if not params:
                return '缺少参数'
            p = _json.loads(params)
            audio_id = p.get('audio_id')
            logger.info(f"[CMD] 收到播放音频指令: audio_id={audio_id}")
            # 从音频库查找文件并发射
            if hasattr(self, 'listener') and self.listener:
                try:
                    from web.models.database import get_db
                except ImportError:
                    return 'Web 模块不可用'
                db_path = os.path.join('data', 'records.db')
                conn = get_db(db_path)
                row = conn.execute('SELECT filepath FROM audio_library WHERE id = ?', (audio_id,)).fetchone()
                conn.close()
                if row and os.path.exists(row['filepath']):
                    self._play_audio_file(row['filepath'])
                    return f'播放完成: {row["filepath"]}'
                return f'音频文件未找到: audio_id={audio_id}'
            return 'listener 未就绪'

        else:
            logger.warning(f"[CMD] 未知命令: {command}")
            return f'未知命令: {command}'

    def _handle_ptt_audio_files(self):
        """从共享缓冲目录读取 PCM 帧文件并发送"""
        ptt_dir = os.path.join('data', 'ptt_buffer')
        if not os.path.isdir(ptt_dir):
            return

        # 按文件名排序（文件名包含 seq 编号）
        files = sorted(f for f in os.listdir(ptt_dir) if f.endswith('.pcm'))
        for fname in files:
            filepath = os.path.join(ptt_dir, fname)
            try:
                with open(filepath, 'rb') as f:
                    pcm_data = f.read()
                os.remove(filepath)
                # 将 PCM 数据发送到 listener 的发射队列
                if hasattr(self, 'listener') and self.listener and hasattr(self.listener, '_tx_queue'):
                    self.listener._tx_queue.put(pcm_data)
            except Exception as e:
                logger.error(f"处理 PTT 音频文件失败 {fname}: {e}")

    def _play_audio_file(self, filepath: str):
        """读取音频文件并通过 listener 发射"""
        import wave
        import subprocess
        import tempfile
        import os

        original_filepath = filepath
        temp_wav = None

        try:
            # 检查文件格式，如果不是 WAV 则转换
            if not filepath.lower().endswith('.wav'):
                logger.info(f"[播放] 检测到非 WAV 格式: {filepath}")

                # 创建临时文件
                temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                temp_wav_path = temp_wav.name
                temp_wav.close()

                logger.info(f"[播放] 使用 ffmpeg 转换为 WAV: {temp_wav_path}")

                # 使用 ffmpeg 转换
                subprocess.run([
                    'ffmpeg', '-y', '-i', filepath,
                    '-ar', '16000',  # 采样率 16kHz
                    '-ac', '1',      # 单声道
                    '-acodec', 'pcm_s16le',  # 16-bit PCM
                    temp_wav_path
                ], check=True, capture_output=True)

                filepath = temp_wav_path
                logger.info(f"[播放] 转换完成")

            self.listener.start_transmit()
            self._last_packet_time = time.time()  # 更新最后音频时间 (TX)
            with wave.open(filepath, 'rb') as wf:
                frame_size = 640  # 320 samples * 2 bytes (16-bit PCM)
                while True:
                    data = wf.readframes(320)
                    if not data or len(data) < frame_size:
                        break
                    if hasattr(self.listener, '_tx_queue'):
                        self.listener._tx_queue.put(data)
                    time.sleep(0.020)  # 20ms per frame
            # 等待最后的帧发送完毕
            time.sleep(0.1)
            self.listener.stop_transmit()
            logger.info(f"[CMD] 音频播放完成: {original_filepath}")

        except Exception as e:
            logger.error(f"播放音频失败: {e}")
            if hasattr(self, 'listener') and self.listener:
                self.listener.stop_transmit()
        finally:
            # 清理临时文件
            if temp_wav and os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                    logger.info(f"[播放] 已删除临时文件: {temp_wav_path}")
                except:
                    pass

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
                            self._last_packet_time = time.time()  # 更新最后音频时间 (TX)
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
    def callback(filepath: str, duration: float, start_time: str, 
                 user_id: str, user_name: str,
                 channel_id: int = 0, recorder_type: str = "RX",
                 lost_frames: int = 0, loss_rate: float = 0.0):
        recognizer.on_recording_complete(
            filepath=filepath,
            duration=duration,
            start_time=start_time,
            user_id=user_id,
            user_name=user_name,
            channel_id=channel_id,
            recorder_type=recorder_type,
            lost_frames=lost_frames,
            loss_rate=loss_rate
        )

        # 广播新录音事件到前端 (WebSocket)
        try:
            broadcast_recording({
                'user_id': user_id,
                'user_name': user_name,
                'duration': duration,
                'timestamp': start_time,
                'channel_id': channel_id,
                'recorder_type': recorder_type,
            })
        except Exception as e:
            logger.warning(f"[录音回调] broadcast_recording 失败: {e}")
    return callback


if __name__ == "__main__":
    # 加载环境变量配置
    import os
    from src.config import load_env_file, get_config
    load_env_file(".env")
    config = get_config()
    
    # 优先使用环境变量中的配置 - 这些必须在try外部定义，确保始终可用
    USERNAME = os.getenv("BSHT_USERNAME", config.bsht.username) or "bswxd"
    PASSWORD = os.getenv("BSHT_PASSWORD", config.bsht.password) or "BsWxd2026"
    
    # 获取频道ID，如果为空或0则交互选择
    env_channel_id = os.getenv("BSHT_CHANNEL_ID", "")
    if env_channel_id:
        try:
            CHANNEL_ID = int(env_channel_id) if env_channel_id else 0
        except ValueError:
            CHANNEL_ID = 0
    else:
        CHANNEL_ID = 0
    
    # 如果没有配置频道ID，交互式选择
    if CHANNEL_ID <= 0:
        print("\n⚠️ 未配置频道ID或ID无效")
        CHANNEL_ID = interactive_select_channel(USERNAME, PASSWORD)
        if CHANNEL_ID <= 0:
            print("❌ 无法获取有效频道ID，退出")
            sys.exit(1)
    
    CHANNEL_PASSCODE = int(os.getenv("BSHT_CHANNEL_PASSCODE", str(config.bsht.channel_passcode)))
    
    try:
        
        print(f"📋 配置加载: 用户={USERNAME}, 频道={CHANNEL_ID}")
        
        if config.api.siliconflow_key:
            # 创建识别器
            from src.recognizer import RecordingRecognizer
            recognizer = RecordingRecognizer(
                api_key=config.api.siliconflow_key
            )
            
            # 伪实时识别已启用
            print("🎯 伪实时识别已启用")
            
            # 设置数据库
            from src.database import get_database
            db = get_database(config.database.path)
            recognizer.set_database(db)

            # 初始化微信推送器
            from src.wx_pusher import init_pusher_from_env_migration, reload_pusher

            # 先尝试从环境变量迁移到数据库
            init_pusher_from_env_migration()

            # 然后从数据库加载（支持热更新）
            pusher = reload_pusher()
            if pusher:
                recognizer.set_pusher(pusher)
                print(f"📲 微信推送已启用 ({len(pusher.targets)} 个目标)")
            else:
                print("📲 微信推送未配置")
            
            # 启动时扫描未入库的录音文件
            print("🔍 扫描历史录音文件...")
            added, processed = recognizer.scan_and_register_recordings("recordings", max_count=50)
            if added > 0 or processed > 0:
                print(f"   📝 新增 {added} 条记录, 识别 {processed} 个文件")
            else:
                print("   ✅ 没有需要处理的历史文件")
            
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
            print("⚠️  API Key未配置，只录制不识别")
            recording_callback = None
    except Exception as e:
        print(f"⚠️  识别器初始化失败: {e}")
        recording_callback = None

    bot = BotServer(USERNAME, PASSWORD, CHANNEL_ID, CHANNEL_PASSCODE)
    try:
        bot.start()
    except KeyboardInterrupt:
        bot.stop()
