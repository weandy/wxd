"""Bot 共享状态管理"""
import threading
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class BotState:
    """Bot 运行状态"""
    running: bool = False
    channel_id: Optional[int] = None
    channel_name: str = ""
    online_count: int = 0
    uptime_start: float = field(default_factory=time.time)
    active_speakers: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default=None)

    def __post_init__(self):
        """初始化后创建锁（避免 dataclass 可变默认值问题）"""
        if self._lock is None:
            object.__setattr__(self, '_lock', threading.Lock())

    def to_dict(self) -> dict:
        """转换为字典"""
        with self._lock:
            uptime = int(time.time() - self.uptime_start)
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60
            seconds = uptime % 60

            return {
                'running': self.running,
                'channel_id': self.channel_id,
                'channel_name': self.channel_name,
                'online_count': self.online_count,
                'uptime': f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s",
                'speakers': {
                    str(uid): data for uid, data in self.active_speakers.items()
                }
            }

    def update(self, **kwargs):
        """更新状态"""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)


# 全局状态实例
_bot_state: Optional[BotState] = None
_bot_state_lock = threading.Lock()


def get_bot_state() -> BotState:
    """获取全局 Bot 状态"""
    global _bot_state
    with _bot_state_lock:
        if _bot_state is None:
            _bot_state = BotState()
        return _bot_state


def reset_bot_state():
    """重置 Bot 状态"""
    global _bot_state
    with _bot_state_lock:
        _bot_state = BotState()
