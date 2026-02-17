# config.py
import os
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class Config:
    SECRET_KEY: str = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
    DEBUG: bool = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    HOST: str = os.getenv('FLASK_HOST', '0.0.0.0')
    PORT: int = int(os.getenv('FLASK_PORT', '5000'))

    BSHT_USERNAME: str = os.getenv('BSHT_USERNAME', '')
    BSHT_PASSWORD: str = os.getenv('BSHT_PASSWORD', '')
    DEFAULT_CHANNEL_ID: int = int(os.getenv('DEFAULT_CHANNEL_ID', '0'))
    DEFAULT_CHANNEL_PASSCODE: int = int(os.getenv('DEFAULT_CHANNEL_PASSCODE', '0'))

    DATABASE_PATH: str = os.getenv('DATABASE_PATH', 'audio.db')
    RECORDINGS_PATH: str = os.getenv('RECORDINGS_PATH', 'recordings')
    RECORDINGS_RETENTION_DAYS: int = int(os.getenv('RECORDINGS_RETENTION_DAYS', '0'))

    STT_SERVICE_URL: Optional[str] = os.getenv('STT_SERVICE_URL')
    STT_API_KEY: Optional[str] = os.getenv('STT_API_KEY')
    TTS_SERVICE_URL: Optional[str] = os.getenv('TTS_SERVICE_URL')
    TTS_API_KEY: Optional[str] = os.getenv('TTS_API_KEY')
    NOTIFICATION_SERVICE_URL: Optional[str] = os.getenv('NOTIFICATION_SERVICE_URL')
    NOTIFICATION_API_KEY: Optional[str] = os.getenv('NOTIFICATION_API_KEY')

    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: str = os.getenv('LOG_FILE', 'bot_web.log')

    @classmethod
    def validate(cls) -> bool:
        if not cls.BSHT_USERNAME:
            logger.error("BSHT_USERNAME 环境变量未设置")
            return False
        if not cls.BSHT_PASSWORD:
            logger.error("BSHT_PASSWORD 环境变量未设置")
            return False
        return True

    @classmethod
    def print_config(cls):
        logger.info(f"配置加载完成:")
        logger.info(f"  FLASK_HOST: {cls.HOST}")
        logger.info(f"  FLASK_PORT: {cls.PORT}")
        logger.info(f"  BSHT_USERNAME: {cls.BSHT_USERNAME}")
        logger.info(f"  DEFAULT_CHANNEL_ID: {cls.DEFAULT_CHANNEL_ID}")
        logger.info(f"  DATABASE_PATH: {cls.DATABASE_PATH}")
        logger.info(f"  RECORDINGS_PATH: {cls.RECORDINGS_PATH}")
