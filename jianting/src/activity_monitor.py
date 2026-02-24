import time
import threading
import logging
from collections import deque
from typing import Dict, List, Callable, Optional

logger = logging.getLogger("VOXMonitor")

class VoiceActivityMonitor:
    """语音活跃度监控器（单例模式）
    
    负责记录接收到的外部音频时间戳，如果指定时间内语音事件达到阈值次，
    则触发绑定的事件回调（用于发送通知或自动回复音频）。
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(VoiceActivityMonitor, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
            
    def __init__(self):
        if self._initialized:
            return
            
        with self._lock:
            if self._initialized:
                return
            
            self._initialized = True
            # {channel_id: deque([timestamp1, timestamp2, ...])}
            self.channel_history: Dict[int, deque] = {}
            # {channel_id: {callback_id: {'seconds': int, 'count': int, 'callback': func, 'last_trigger': float}}}
            self.rules: Dict[int, Dict[str, dict]] = {}
            self.data_lock = threading.Lock()
            
            # 全局配置缓存
            self.global_enabled = False
            self.global_seconds = 10
            self.global_count = 3
            self.global_last_trigger = 0.0
            
            # 开启异步拉取全局设定的线程
            threading.Thread(target=self._global_config_loop, daemon=True).start()
            
            logger.info("[VOXMonitor] 语音监控器初始化完毕")

    def _global_config_loop(self):
        """后台轮询获取全局 VOX 告警配置和自动回复任务"""
        import sqlite3
        import os
        import json
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'records.db'
        )
        while True:
            try:
                if os.path.exists(db_path):
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    # 1. 加载全局告警配置
                    cursor.execute("SELECT key, value FROM config WHERE key IN ('VOX_ALERT_ENABLED', 'VOX_ALERT_SECONDS', 'VOX_ALERT_COUNT')")
                    rows = cursor.fetchall()
                    config = {k: v for k, v in rows}
                    
                    # 2. 加载触发类型为 voice 的可用预定义任务
                    cursor.execute("SELECT id, channel_id, schedule_config FROM scheduled_tasks WHERE trigger_type = 'voice' AND enabled = 1")
                    tasks = cursor.fetchall()
                    
                    conn.close()
                    
                    with self.data_lock:
                        # 更新告警开关
                        self.global_enabled = (config.get('VOX_ALERT_ENABLED') == '1')
                        try:
                            self.global_seconds = int(config.get('VOX_ALERT_SECONDS', 10))
                            self.global_count = int(config.get('VOX_ALERT_COUNT', 3))
                        except ValueError:
                            pass
                            
                        # 更新自动回复任务集合
                        new_rules = {}
                        for t_id, c_id, conf_str in tasks:
                            if c_id not in new_rules:
                                new_rules[c_id] = {}
                            try:
                                cfg = json.loads(conf_str) if conf_str else {}
                                seconds = int(cfg.get('seconds', 10))
                                count = int(cfg.get('count', 3))
                                r_id = str(t_id)
                                
                                # 取回之前该任务的 cooldown，以免重置导致刷屏
                                last_trig = 0.0
                                if c_id in self.rules and r_id in self.rules[c_id]:
                                    last_trig = self.rules[c_id][r_id]['last_trigger']
                                
                                # 构建闭包，绑定 t_id
                                def make_cb(task_id):
                                    return lambda ch: self._trigger_voice_task(task_id)
                                    
                                new_rules[c_id][r_id] = {
                                    'seconds': seconds,
                                    'count': count,
                                    'callback': make_cb(t_id),
                                    'last_trigger': last_trig
                                }
                            except Exception:
                                pass
                        self.rules = new_rules
                        
            except Exception as e:
                logger.debug(f"[VOXMonitor] 读取全局配置失败: {e}")
            
            time.sleep(10)  # 每 10 秒刷新一次
            
    def _trigger_voice_task(self, task_id: int):
        """执行指定定时任务的音频发射操作"""
        import sqlite3
        import os
        from web.routes.bot import _decode_audio_to_pcm, _broadcast_pcm
        from web.bot_bridge import get_bot_listener
        
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'records.db'
        )
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.*, a.filepath as audio_filepath, a.name as audio_name
                FROM scheduled_tasks t
                LEFT JOIN audio_library a ON t.audio_id = a.id
                WHERE t.id = ?
            ''', (task_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row or not row['audio_filepath'] or not os.path.exists(row['audio_filepath']):
                logger.error(f"[VOXMonitor] 任务 {task_id} 音频文件不存在")
                return
                
            listener = get_bot_listener()
            if not listener:
                logger.error("[VOXMonitor] 未连接到游戏/平台频道")
                return
                
            with open(row['audio_filepath'], 'rb') as f:
                audio_data = f.read()
                
            pcm, src_rate = _decode_audio_to_pcm(audio_data)
            if pcm is None:
                logger.error("[VOXMonitor] 音频解析失败")
                return
                
            duration, frames = _broadcast_pcm(pcm, src_rate, listener)
            logger.info(f"[VOXMonitor] 任务 {task_id} 频道内高频语音触发自动回复完成 ({duration}s)")
            
            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE scheduled_tasks SET last_run_at = datetime('now') WHERE id = ?", (task_id,))
            conn.execute("INSERT INTO scheduled_task_logs (task_id, status, message, executed_at) VALUES (?, ?, ?, datetime('now'))",
                (task_id, 'success', f'VOX 自动回复发射: {duration}s'))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[VOXMonitor] VOX 触发回调任务执行异常: {e}")

    def _trigger_global_alert(self, channel_id: int):
        """触发全局微信推送告警"""
        try:
            from src.wx_pusher import get_pusher
            pusher = get_pusher()
            if pusher:
                pusher.send(
                    title="⚠️ 频道高频语音预警",
                    content=f"监控到频道 (ID: {channel_id}) 内有频繁的语音输入活动，请注意查看是否有呼叫请求。"
                )
                logger.info("[VOXMonitor] 已发送全局语音高频预警推送")
        except Exception as e:
            logger.error(f"[VOXMonitor] 发送预警推送异常: {e}")

    def register_rule(self, channel_id: int, rule_id: str, seconds: int, count: int, callback: Callable):
        """为频道注册一个高频触发规则"""
        with self.data_lock:
            if channel_id not in self.rules:
                self.rules[channel_id] = {}
            
            self.rules[channel_id][rule_id] = {
                'seconds': seconds,
                'count': count,
                'callback': callback,
                'last_trigger': 0.0  # COOLDOWN 检测
            }
            logger.info(f"[VOXMonitor] 注册规则: channel={channel_id}, id={rule_id}, 条件: {seconds}秒内{count}次")

    def unregister_rule(self, channel_id: int, rule_id: str):
        """移除规则"""
        with self.data_lock:
            if channel_id in self.rules and rule_id in self.rules[channel_id]:
                del self.rules[channel_id][rule_id]

    def record_activity(self, channel_id: int, user_id: int):
        """记录一次外部语音接入（Bot自身的可以忽略，但通常 bot_server 调过来的是别人发送的）"""
        now = time.time()
        
        with self.data_lock:
            if channel_id not in self.channel_history:
                self.channel_history[channel_id] = deque()
            
            # 由于实时帧来得太快，为了防抖，只记录“句子”级别或者每隔 1 秒一次，
            # 若和上一次时间间隔太小（如 < 1秒），则不重复计次（认为是一次连续讲话）。
            # 注意：实际这里触发的可能是按包粒度，所以必须引入句内防抖。
            history = self.channel_history[channel_id]
            if history and (now - history[-1]) < 1.0:
                pass # 距离上次说话不到1秒，判定为同一次持续讲话，不增加新的时间戳计数
            else:
                history.append(now)
                
            # 清理过期的记录（只保留最长可能的窗口，假设最大不过 3600 秒）
            MAX_WINDOW = 3600
            while history and (now - history[0]) > MAX_WINDOW:
                history.popleft()
                
            # 校验特定规则 (比如定时任务设置的自回复)
            if channel_id in self.rules:
                for r_id, rule in self.rules[channel_id].items():
                    self._check_and_trigger(channel_id, r_id, rule, history, now)

            # 校验全局告警规则
            if getattr(self, 'global_enabled', False):
                self._check_and_trigger_global(channel_id, history, now)

    def _check_and_trigger_global(self, channel_id: int, history: deque, now: float):
        """校验如果满足全局规则就触发推送"""
        cooldown = 30.0 # 推送的冷却时间设为 30 秒防报警轰炸
        if (now - self.global_last_trigger) < cooldown:
            return

        valid_count = sum(1 for ts in history if (now - ts) <= self.global_seconds)
        if valid_count >= self.global_count:
            self.global_last_trigger = now
            threading.Thread(target=self._trigger_global_alert, args=(channel_id,), daemon=True).start()

    def _check_and_trigger(self, channel_id: int, rule_id: str, rule: dict, history: deque, now: float):
        """校验如果满足规则就触发"""
        cooldown = 15.0 # 写死 15 秒冷却时间防刷屏
        if (now - rule['last_trigger']) < cooldown:
            return  # 还在冷却中

        # 计算落在窗口内的次数
        valid_count = sum(1 for ts in history if (now - ts) <= rule['seconds'])
        
        if valid_count >= rule['count']:
            logger.info(f"[VOXMonitor] 触发警报! channel={channel_id}, rule={rule_id}, 统计={valid_count}次")
            rule['last_trigger'] = now
            # 触发回调
            try:
                # 为了不阻塞当前的音频工作线程，扔到后台线程执行
                threading.Thread(target=rule['callback'], args=(channel_id,), daemon=True).start()
            except Exception as e:
                logger.error(f"[VOXMonitor] 执行回调失败 {rule_id}: {e}")

# 全局单例
monitor = VoiceActivityMonitor()
