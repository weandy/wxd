"""
数据库异步优化模块

为现有数据库操作提供异步支持：
1. 异步查询包装器
2. 连接池集成
3. 批量操作优化
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class AsyncDatabaseWrapper:
    """
    异步数据库包装器

    用途:
    - 在不阻塞主线程的情况下执行数据库操作
    - 支持批量操作
    - 自动连接池管理
    """

    def __init__(self, db_instance, max_workers: int = 4):
        """
        Args:
            db_instance: 现有数据库实例
            max_workers: 线程池大小
        """
        self._db = db_instance
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="db_worker"
        )
        logger.info("异步数据库包装器初始化完成")

    async def add_recording(self, recording: dict) -> int:
        """异步添加录音记录"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._add_recording_sync,
            recording
        )

    def _add_recording_sync(self, recording: dict) -> int:
        """同步添加录音记录"""
        try:
            # 使用现有的add_recording方法
            from src.database import Recording

            rec = Recording(
                filepath=recording.get('filepath', ''),
                filename=recording.get('filename', ''),
                channel_id=recording.get('channel_id', 0),
                user_id=str(recording.get('user_id', '')),
                user_name=recording.get('user_name', ''),
                recorder_type=recording.get('recorder_type', 'RX'),
                duration=recording.get('duration', 0),
                start_time=recording.get('start_time', ''),
                file_size=recording.get('file_size', 0),
                timestamp=recording.get('timestamp', ''),
                recognized=recording.get('recognized', False)
            )

            return self._db.add_recording(rec)

        except Exception as e:
            logger.error(f"添加录音记录失败: {e}")
            return -1

    async def update_recognition(self, filepath: str, asr_text: str,
                                signal_type: str, confidence: float,
                                rms_db: float = 0, snr_db: float = 0) -> bool:
        """异步更新识别结果"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._update_recognition_sync,
            filepath, asr_text, signal_type, confidence, rms_db, snr_db
        )

    def _update_recognition_sync(self, filepath: str, asr_text: str,
                                signal_type: str, confidence: float,
                                rms_db: float, snr_db: float) -> bool:
        """同步更新识别结果"""
        try:
            self._db.update_recording_recognition(
                filepath=filepath,
                asr_text=asr_text,
                content_normalized=asr_text,
                signal_type=signal_type,
                confidence=confidence,
                rms_db=rms_db,
                snr_db=snr_db
            )
            return True
        except Exception as e:
            logger.error(f"更新识别结果失败: {e}")
            return False

    async def get_recording(self, filepath: str) -> Optional[dict]:
        """异步获取录音记录"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._get_recording_sync,
            filepath
        )

    def _get_recording_sync(self, filepath: str) -> Optional[dict]:
        """同步获取录音记录"""
        try:
            result = self._db.get_recording_by_path(filepath)
            if result:
                return {
                    'filepath': result.filepath,
                    'filename': result.filename,
                    'channel_id': result.channel_id,
                    'user_id': result.user_id,
                    'user_name': result.user_name,
                    'duration': result.duration,
                    'recognized': result.recognized,
                    'signal_type': result.signal_type,
                    'confidence': result.confidence
                }
            return None
        except Exception as e:
            logger.error(f"获取录音记录失败: {e}")
            return None

    async def batch_update(self, updates: List[dict]) -> int:
        """异步批量更新"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._batch_update_sync,
            updates
        )

    def _batch_update_sync(self, updates: List[dict]) -> int:
        """同步批量更新"""
        count = 0
        for update in updates:
            if self._update_recognition_sync(
                update['filepath'],
                update.get('asr_text', ''),
                update.get('signal_type', 'UNKNOWN'),
                update.get('confidence', 0),
                update.get('rms_db', 0),
                update.get('snr_db', 0)
            ):
                count += 1
        return count

    def shutdown(self):
        """关闭线程池"""
        self._executor.shutdown(wait=True)
        logger.info("异步数据库包装器已关闭")


# 全局实例
_global_async_db: Optional[AsyncDatabaseWrapper] = None
_db_lock = threading.Lock()


def get_async_database(db_instance) -> AsyncDatabaseWrapper:
    """获取异步数据库包装器"""
    global _global_async_db

    with _db_lock:
        if _global_async_db is None:
            _global_async_db = AsyncDatabaseWrapper(db_instance)

        return _global_async_db


import threading
