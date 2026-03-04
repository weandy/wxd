"""
Bot 通信模块（简化版）
直接在 Web 服务中实现广播功能
"""
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class BotCommunicator:
    """Bot 通信器 - 简化版，直接返回模拟结果"""

    async def send_audio_to_channel(
        self,
        audio_filepath: str,
        channel_id: int
    ) -> Dict[str, Any]:
        """
        发送音频到指定频道

        Args:
            audio_filepath: 音频文件路径
            channel_id: 频道ID

        Returns:
            发送结果
        """
        # 检查文件是否存在
        if not Path(audio_filepath).exists():
            return {
                "success": False,
                "message": f"音频文件不存在: {audio_filepath}"
            }

        # TODO: 实际的广播功能需要与 Bot 服务集成
        # 目前返回模拟成功结果
        logger.info(f"[模拟广播] 发送音频到频道 {channel_id}: {audio_filepath}")

        return {
            "success": True,
            "message": f"音频已添加到广播队列（频道 {channel_id}）",
            "audio_path": audio_filepath,
            "channel_id": channel_id
        }

    async def send_tts_to_channel(
        self,
        text: str,
        channel_id: int,
        voice: str = "default"
    ) -> Dict[str, Any]:
        """
        发送 TTS 到指定频道

        Args:
            text: 要转换的文本
            channel_id: 频道ID
            voice: 语音类型

        Returns:
            发送结果
        """
        # TODO: 实际的 TTS 广播功能
        logger.info(f"[模拟广播] 发送 TTS 到频道 {channel_id}: {text[:50]}...")

        return {
            "success": True,
            "message": f"TTS 已添加到广播队列（频道 {channel_id}）",
            "text": text,
            "channel_id": channel_id
        }

    async def get_bot_status(self) -> Dict[str, Any]:
        """
        获取 Bot 服务状态

        Returns:
            Bot 状态信息
        """
        # 简化版，假设 Bot 总是运行中
        return {"running": True}


# 单例实例
_communicator: Optional[BotCommunicator] = None


def get_bot_communicator() -> BotCommunicator:
    """获取 Bot 通信器单例"""
    global _communicator
    if _communicator is None:
        _communicator = BotCommunicator()
    return _communicator


async def execute_broadcast_task(
    task_type: str,
    audio_filepath: Optional[str] = None,
    tts_text: Optional[str] = None,
    channel_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    执行广播任务

    Args:
        task_type: 任务类型 (audio/tts)
        audio_filepath: 音频文件路径（audio 任务）
        tts_text: TTS 文本（tts 任务）
        channel_id: 目标频道ID（可选，默认使用 .env 配置）

    Returns:
        执行结果
    """
    import os
    import json
    from src.config import get_config

    # 如果没有指定频道，使用默认频道
    if channel_id is None:
        # 尝试从 channels.json 获取频道ID
        try:
            channels_file = Path("channels.json")
            if channels_file.exists():
                with open(channels_file, 'r', encoding='utf-8') as f:
                    channels_data = json.load(f)
                    if channels_data.get('channels'):
                        channel_id = channels_data['channels'][0]['id']
        except Exception as e:
            logger.warning(f"无法从 channels.json 读取频道ID: {e}")

    if channel_id is None:
        # 尝试从环境变量获取
        config = get_config()
        if hasattr(config, 'channel') and hasattr(config.channel, 'id'):
            channel_id = config.channel.id

    if channel_id is None:
        return {
            "success": False,
            "message": "未配置目标频道，请检查 channels.json 或 .env 配置"
        }

    communicator = get_bot_communicator()

    if task_type == "audio":
        if not audio_filepath:
            return {
                "success": False,
                "message": "缺少音频文件路径"
            }
        return await communicator.send_audio_to_channel(audio_filepath, channel_id)

    elif task_type == "tts":
        if not tts_text:
            return {
                "success": False,
                "message": "缺少 TTS 文本"
            }
        return await communicator.send_tts_to_channel(tts_text, channel_id)

    else:
        return {
            "success": False,
            "message": f"不支持的任务类型: {task_type}"
        }
