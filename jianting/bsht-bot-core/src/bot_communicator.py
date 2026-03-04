"""
Bot 通信模块
用于 Web 服务器与 Bot 服务之间的通信
"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import aiohttp

logger = logging.getLogger(__name__)


class BotCommunicator:
    """Bot 通信器 - 通过 WebSocket 或 HTTP 与 Bot 服务通信"""

    def __init__(self, bot_host: str = "localhost", bot_port: int = 8765):
        self.bot_host = bot_host
        self.bot_port = bot_port
        self.base_url = f"http://{bot_host}:{bot_port}"
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

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
        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            # 检查文件是否存在
            if not Path(audio_filepath).exists():
                return {
                    "success": False,
                    "message": f"音频文件不存在: {audio_filepath}"
                }

            # 调用 Bot 的音频广播接口
            url = f"{self.base_url}/api/broadcast/audio"
            payload = {
                "audio_path": audio_filepath,
                "channel_id": channel_id
            }

            async with self.session.post(url, json=payload, timeout=30) as response:
                result = await response.json()

                if response.status == 200:
                    return {
                        "success": True,
                        "message": "音频广播成功",
                        "data": result
                    }
                else:
                    return {
                        "success": False,
                        "message": result.get("message", "广播失败")
                    }

        except aiohttp.ClientError as e:
            logger.error(f"Bot 通信失败: {e}")
            return {
                "success": False,
                "message": f"无法连接到 Bot 服务: {str(e)}"
            }
        except Exception as e:
            logger.error(f"音频广播失败: {e}")
            return {
                "success": False,
                "message": f"广播失败: {str(e)}"
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
        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            url = f"{self.base_url}/api/broadcast/tts"
            payload = {
                "text": text,
                "channel_id": channel_id,
                "voice": voice
            }

            async with self.session.post(url, json=payload, timeout=30) as response:
                result = await response.json()

                if response.status == 200:
                    return {
                        "success": True,
                        "message": "TTS 广播成功",
                        "data": result
                    }
                else:
                    return {
                        "success": False,
                        "message": result.get("message", "TTS 广播失败")
                    }

        except Exception as e:
            logger.error(f"TTS 广播失败: {e}")
            return {
                "success": False,
                "message": f"TTS 广播失败: {str(e)}"
            }

    async def get_bot_status(self) -> Dict[str, Any]:
        """
        获取 Bot 服务状态

        Returns:
            Bot 状态信息
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            url = f"{self.base_url}/api/status"
            async with self.session.get(url, timeout=5) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"running": False}
        except Exception as e:
            logger.debug(f"获取 Bot 状态失败: {e}")
            return {"running": False}


# 单例实例
_communicator: Optional[BotCommunicator] = None


def get_bot_communicator() -> BotCommunicator:
    """获取 Bot 通信器单例"""
    global _communicator
    if _communicator is None:
        import os
        bot_host = os.getenv("BOT_HOST", "localhost")
        bot_port = int(os.getenv("BOT_PORT", "8765"))
        _communicator = BotCommunicator(bot_host, bot_port)
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
    from src.config import get_config

    # 获取配置
    config = get_config()

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
        except:
            pass

    if channel_id is None:
        return {
            "success": False,
            "message": "未配置目标频道"
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
