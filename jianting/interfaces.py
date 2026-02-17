# interfaces.py
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass
from enum import Enum

class BotState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class BotStatus:
    state: BotState = BotState.STOPPED
    connected_channel: Optional[int] = None
    is_transmitting: bool = False
    current_speakers: list = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.current_speakers is None:
            self.current_speakers = []


class IEventHandler(ABC):
    """事件处理器接口"""

    def on_audio_recorded(self, recording):
        pass

    def on_message_received(self, channel_id: int, user_id: int, content: str):
        pass

    def on_speaker_started(self, channel_id: int, user_id: int, username: str):
        pass

    def on_speaker_stopped(self, channel_id: int, user_id: int):
        pass

    def on_transmit_started(self):
        pass

    def on_transmit_stopped(self):
        pass

    def on_bot_state_changed(self, status: BotStatus):
        pass


class IRecordingManager(ABC):
    """录音管理器接口"""

    @abstractmethod
    def start_recording(self, channel_id: int):
        pass

    @abstractmethod
    def stop_recording(self, channel_id: int):
        pass

    @abstractmethod
    def is_recording(self, channel_id: int) -> bool:
        pass
