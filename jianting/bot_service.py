# bot_service.py
import threading
import logging
from typing import Optional, List, Dict
from interfaces import IEventHandler, BotState, BotStatus, IRecordingManager
from database import Channel, Recording, ChannelRepository, RecordingRepository

logger = logging.getLogger(__name__)


class DefaultEventHandler(IEventHandler):
    """默认事件处理器"""
    pass


class ChannelRecordingManager(IRecordingManager):
    """频道录音管理器"""

    def __init__(self, recording_repo: RecordingRepository, base_path: str = "recordings"):
        self._repo = recording_repo
        self._base_path = base_path
        self._active_recordings: Dict[int, any] = {}

    def start_recording(self, channel_id: int):
        if channel_id in self._active_recordings:
            return

        from channel_recorder import ChannelRecorder
        recorder = ChannelRecorder(channel_id=channel_id, base_path=self._base_path)
        recorder.start()
        self._active_recordings[channel_id] = recorder
        logger.info(f"开始录音频道 {channel_id}")

    def stop_recording(self, channel_id: int):
        if channel_id not in self._active_recordings:
            return

        recorder = self._active_recordings.pop(channel_id)

        # 获取录音记录
        recordings = recorder.get_recordings() if hasattr(recorder, 'get_recordings') else []

        for rec in recordings:
            self._repo.add(rec)

        logger.info(f"停止录音频道 {channel_id}")

    def is_recording(self, channel_id: int) -> bool:
        return channel_id in self._active_recordings


class BotService:
    """Bot 核心服务"""

    def __init__(self,
                 username: str,
                 password: str,
                 channel_repo: ChannelRepository,
                 recording_repo: RecordingRepository,
                 event_handler: Optional[IEventHandler] = None):
        self._channel_repo = channel_repo
        self._recording_repo = recording_repo
        self._event_handler = event_handler or DefaultEventHandler()

        self._client = None
        self._username = username
        self._password = password

        self._recording_manager = ChannelRecordingManager(recording_repo)
        self._status = BotStatus()
        self._lock = threading.Lock()
        self._listener = None

    @property
    def client(self):
        if self._client is None:
            from bsht_client import BSHTClient
            self._client = BSHTClient(auto_refresh_token=True)
            self._client.set_token_refresh_callback(self._on_token_refreshed)
        return self._client

    def start(self) -> bool:
        with self._lock:
            if self._status.state != BotState.STOPPED:
                return False
            self._update_state(BotState.STARTING)

        try:
            if not self._login():
                self._update_state(BotState.ERROR, "登录失败")
                return False

            self._join_auto_channels()
            self._update_state(BotState.RUNNING)
            return True
        except Exception as e:
            logger.error(f"启动失败: {e}")
            self._update_state(BotState.ERROR, str(e))
            return False

    def stop(self):
        with self._lock:
            if self._status.state == BotState.STOPPED:
                return
            self._update_state(BotState.STOPPING)

        try:
            for channel_id in list(self._recording_manager._active_recordings.keys()):
                self._recording_manager.stop_recording(channel_id)

            if self._listener:
                self._listener.stop()
                self._listener = None

            if self._client:
                self._client.close()

            self._update_state(BotState.STOPPED)
        except Exception as e:
            logger.error(f"停止时出错: {e}")

    def get_status(self) -> BotStatus:
        with self._lock:
            return BotStatus(
                state=self._status.state,
                connected_channel=self._status.connected_channel,
                is_transmitting=self._status.is_transmitting,
                current_speakers=list(self._status.current_speakers),
                error_message=self._status.error_message
            )

    def join_channel(self, channel_id: int, passcode: int = 0) -> bool:
        try:
            result = self.client.get_channel_connection_params(channel_id, passcode)
            if not result.success:
                return False

            from bsht_client import AudioStreamListener
            params = result.data
            self._listener = AudioStreamListener(
                self.client,
                server_ip=params.server_ip,
                server_port=params.server_port
            )
            self._listener.start()

            with self._lock:
                self._status.connected_channel = channel_id

            self._recording_manager.start_recording(channel_id)
            self._event_handler.on_bot_state_changed(self.get_status())
            return True
        except Exception as e:
            logger.error(f"加入频道失败: {e}")
            return False

    def leave_channel(self):
        if not self._listener:
            return

        channel_id = self._status.connected_channel
        self._recording_manager.stop_recording(channel_id)
        self._listener.stop()
        self._listener = None

        with self._lock:
            self._status.connected_channel = None

        self._event_handler.on_bot_state_changed(self.get_status())

    def get_channels(self) -> List[Channel]:
        result = self.client.get_channels()
        if result.success:
            return [Channel(channel_id=ch.id, name=ch.name) for ch in result.data]
        return []

    def start_transmit(self) -> bool:
        if not self._listener:
            return False
        self._listener.start_transmit()
        with self._lock:
            self._status.is_transmitting = True
        self._event_handler.on_transmit_started()
        return True

    def stop_transmit(self) -> bool:
        if not self._listener:
            return False
        self._listener.stop_transmit()
        with self._lock:
            self._status.is_transmitting = False
        self._event_handler.on_transmit_stopped()
        return True

    def _login(self) -> bool:
        if self.client.load_credentials():
            if self.client.load_profile().success:
                return True

        result = self.client.login(self._username, self._password)
        if result.success:
            self.client.load_profile()
            self.client.save_credentials()
            return True
        return False

    def _join_auto_channels(self):
        auto_channels = self._channel_repo.list_by_auto_join(True)
        for channel in auto_channels:
            self.join_channel(channel.channel_id, channel.passcode)

    def _on_token_refreshed(self, token_info):
        self.client.save_credentials()

    def _update_state(self, state: BotState, error: Optional[str] = None):
        self._status.state = state
        self._status.error_message = error
        self._event_handler.on_bot_state_changed(self.get_status())
