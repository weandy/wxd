"""TTS 语音合成模块"""

import os
import httpx
import wave
import io
import base64
import uuid
from datetime import datetime


class TTSEngine:
    """TTS 引擎封装"""

    # 可用声音列表
    VOICES = [
        ("zh-CN-XiaoxiaoNeural", "晓晓-女声"),
        ("zh-CN-YunxiNeural", "云希-男声"),
        ("zh-CN-YunjianNeural", "云健-新闻男声"),
        ("zh-CN-XiaoyiNeural", "晓伊-甜美女声"),
        ("zh-CN-XiaomoNeural", "晓墨-温柔女声"),
        ("zh-CN-XiaoxuanNeural", "晓璇-专业女声"),
        ("zh-CN-YunyangNeural", "云扬-标准男声"),
    ]

    def __init__(self, worker_url=None, default_voice=None, default_speed=None):
        """初始化 TTS 引擎"""
        self.worker_url = worker_url or os.getenv('TTS_WORKER_URL', 'https://tts.cnleestar.workers.dev')
        self.default_voice = default_voice or os.getenv('TTS_DEFAULT_VOICE', 'zh-CN-YunxiNeural')
        self.default_speed = float(default_speed or os.getenv('TTS_DEFAULT_SPEED', '1.0'))

    async def synthesize(self, text: str, voice: str = None, speed: float = None) -> bytes:
        """
        合成语音，返回 WAV 格式音频数据

        Args:
            text: 要合成的文本
            voice: 声音ID，默认使用配置的声音
            speed: 语速，1.0 为正常速度

        Returns:
            WAV 格式的音频数据 (bytes)
        """
        voice = voice or self.default_voice
        speed = speed if speed is not None else self.default_speed

        # 构建请求
        url = f"{self.worker_url}/v1/audio/speech"
        payload = {
            "input": text,
            "voice": voice,
            "speed": speed,
            "response_format": "wav"
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.content

    async def preview(self, text: str, voice: str = None, speed: float = None) -> str:
        """
        生成预览音频，返回 base64 编码的音频

        Args:
            text: 要合成的文本
            voice: 声音ID
            speed: 语速

        Returns:
            base64 编码的音频字符串 (可直接用于 audio src)
        """
        wav_data = await self.synthesize(text, voice, speed)
        return base64.b64encode(wav_data).decode('utf-8')

    def save_to_file(self, wav_data: bytes, filename: str = None, upload_dir: str = None) -> tuple:
        """
        保存 WAV 数据到文件

        Args:
            wav_data: WAV 格式的音频数据
            filename: 文件名（不含扩展名），默认自动生成
            upload_dir: 上传目录，默认使用音频库目录

        Returns:
            (filepath, duration, file_size) 元组
        """
        if upload_dir is None:
            upload_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'data', 'audio_library'
            )
        os.makedirs(upload_dir, exist_ok=True)

        # 生成文件名
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"tts_{timestamp}_{uuid.uuid4().hex[:6]}"

        # 确保是 WAV 扩展名
        if not filename.lower().endswith('.wav'):
            filename += '.wav'

        filepath = os.path.join(upload_dir, filename)

        # 写入文件
        with open(filepath, 'wb') as f:
            f.write(wav_data)

        file_size = len(wav_data)

        # 读取时长
        duration = 0
        try:
            # 先尝试用返回的数据直接解析
            with wave.open(io.BytesIO(wav_data)) as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                duration = round(frames / rate, 1)
        except Exception:
            # 如果解析失败，尝试保存后再读取
            try:
                with wave.open(filepath, 'r') as wav:
                    frames = wav.getnframes()
                    rate = wav.getframerate()
                    duration = round(frames / rate, 1)
            except Exception:
                pass

        return filepath, duration, file_size

    @staticmethod
    def get_voices() -> list:
        """获取可用声音列表"""
        return TTSEngine.VOICES

    @staticmethod
    def get_voice_name(voice_id: str) -> str:
        """根据声音ID获取显示名称"""
        for vid, name in TTSEngine.VOICES:
            if vid == voice_id:
                return name
        return voice_id
