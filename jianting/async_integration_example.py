"""
异步优化集成示例

展示如何在现有代码中集成异步优化功能
基于 bot_server.py 的改造示例
"""

import time
import threading
import asyncio
import logging
from typing import Optional

# 导入异步优化模块
from async_optimization import (
    get_metrics_collector,
    get_thread_pool,
    get_optimizer,
    timed_sync,
    run_in_pool,
    PerformanceOptimizer
)
from async_database_wrapper import get_async_database

logger = logging.getLogger(__name__)


class OptimizedBotServer:
    """
    优化后的机器人服务器示例

    展示如何在现有 BotServer 中集成异步优化
    """

    def __init__(self, username: str, password: str, channel_id: int):
        self.username = username
        self.password = password
        self.channel_id = channel_id

        # ==================== 1. 初始化性能优化组件 ====================

        # 性能指标收集器
        self.metrics = get_metrics_collector()

        # 线程池管理器
        self.thread_pool = get_thread_pool()

        # 性能优化器
        self.optimizer = get_optimizer()

        # ==================== 2. 启动监控线程 ====================

        # 启动性能报告线程
        self._metrics_thread = threading.Thread(
            target=self._metrics_reporter,
            daemon=True
        )
        self._metrics_thread.start()

        logger.info("性能优化组件初始化完成")

    def _metrics_reporter(self):
        """定期报告性能指标"""
        while True:
            time.sleep(60)  # 每分钟报告
            self.metrics.print_summary()

    # ==================== 3. 使用计时装饰器 ====================

    @timed_sync("bot_server.login")
    def login(self) -> bool:
        """登录 - 自动计时"""
        start = time.time()

        try:
            # 原有登录逻辑
            result = self._do_login()
            return result
        finally:
            duration = time.time() - start
            logger.info(f"登录耗时: {duration*1000:.2f}ms")

    @timed_sync("bot_server.join_channel")
    def join_channel(self) -> bool:
        """加入频道 - 自动计时"""
        start = time.time()

        try:
            # 原有加入频道逻辑
            result = self._do_join_channel()
            return result
        finally:
            duration = time.time() - start
            logger.info(f"加入频道耗时: {duration*1000:.2f}ms")

    @timed_sync("bot_server.get_channels")
    def get_channels(self) -> list:
        """获取频道列表 - 自动计时"""
        start = time.time()

        try:
            # 原有逻辑
            result = self._do_get_channels()
            return result
        finally:
            duration = time.time() - start
            self.metrics.record("get_channels", duration)

    # ==================== 4. 使用线程池处理CPU密集型任务 ====================

    def process_audio_async(self, audio_data: bytes):
        """
        异步处理音频数据

        将CPU密集型的音频处理放到线程池中执行
        不阻塞主接收线程
        """
        # 提交到CPU线程池
        future = self.thread_pool.submit_cpu(
            self._heavy_audio_processing,
            audio_data
        )

        # 可以选择等待结果或继续处理
        # 方式1: 立即返回 Future
        return future

        # 方式2: 等待结果
        # return future.result(timeout=1.0)

    def _heavy_audio_processing(self, audio_data: bytes) -> bytes:
        """
        CPU密集型音频处理

        例如:
        - 噪声抑制
        - 音频增强
        - 频谱分析
        """
        # 模拟CPU密集型处理
        time.sleep(0.01)  # 10ms 处理时间

        # 实际处理逻辑...
        return audio_data

    # ==================== 5. 使用线程池装饰器 ====================

    @run_in_pool(pool_type="cpu")
    def analyze_audio(self, audio_data: bytes) -> dict:
        """分析音频 - 自动在线程池执行"""
        # CPU密集型分析
        result = {
            'rms': 0.5,
            'snr': 20.0,
            'has_voice': True
        }
        return result

    @run_in_pool(pool_type="audio")
    def encode_audio(self, audio_data: bytes) -> bytes:
        """编码音频 - 使用专用音频线程池"""
        # 音频编码
        return audio_data

    # ==================== 6. 异步数据库操作 ====================

    async def save_recording_async(self, recording: dict):
        """
        异步保存录音记录

        不阻塞主线程
        """
        from src.database import get_database

        # 获取异步数据库包装器
        async_db = get_async_database(get_database())

        # 异步添加记录
        record_id = await async_db.add_recording(recording)

        logger.info(f"录音记录已保存: ID={record_id}")
        return record_id

    async def update_recognition_async(self, filepath: str, result: dict):
        """异步更新识别结果"""
        from src.database import get_database

        async_db = get_async_database(get_database())

        await async_db.update_recognition(
            filepath=filepath,
            asr_text=result.get('text', ''),
            signal_type=result.get('type', 'UNKNOWN'),
            confidence=result.get('confidence', 0),
            rms_db=result.get('rms_db', 0),
            snr_db=result.get('snr_db', 0)
        )

    # ==================== 7. 批量处理 ====================

    async def batch_process_recordings(self, recordings: list):
        """
        批量处理录音

        使用性能优化器的并发批处理
        """
        async def process_single(recording: dict):
            # 处理单个录音
            result = await self._process_recording(recording)
            return result

        # 并发处理
        results = await self.optimizer.batch_process(
            items=recordings,
            processor=process_single,
            max_concurrency=5
        )

        return results

    async def _process_recording(self, recording: dict) -> dict:
        """处理单个录音"""
        # 模拟处理
        await asyncio.sleep(0.1)
        return {'status': 'processed', 'filepath': recording.get('filepath')}

    # ==================== 8. 原有方法 (保持不变) ====================

    def _do_login(self) -> bool:
        """原有登录逻辑"""
        return True

    def _do_join_channel(self) -> bool:
        """原有加入频道逻辑"""
        return True

    def _do_get_channels(self) -> list:
        """原有获取频道列表"""
        return []

    # ==================== 9. 清理资源 ====================

    async def cleanup(self):
        """清理资源"""
        logger.info("清理性能优化资源...")

        # 关闭异步HTTP客户端
        await self.optimizer.cleanup()

        # 关闭数据库包装器
        # async_db.shutdown()  # 如果需要

        logger.info("资源清理完成")


# ==================== 使用示例 ====================

def example_usage():
    """使用示例"""

    # 创建优化后的服务器
    server = OptimizedBotServer(
        username="test_user",
        password="test_pass",
        channel_id=12345
    )

    # 使用计时装饰器的方法
    success = server.login()
    channels = server.get_channels()

    # 使用线程池处理CPU密集型任务
    audio_data = b"test audio data"
    future = server.process_audio_async(audio_data)
    result = future.result()  # 获取结果

    # 使用装饰器
    analysis = server.analyze_audio(audio_data)

    # 打印性能指标
    server.metrics.print_summary()

    print("✅ 示例运行完成")


def example_async_usage():
    """异步使用示例"""

    async def main():
        server = OptimizedBotServer(
            username="test_user",
            password="test_pass",
            channel_id=12345
        )

        # 异步保存录音
        recording = {
            'filepath': 'test.wav',
            'filename': 'test.wav',
            'channel_id': 12345,
            'user_id': '123',
            'user_name': 'Test User',
            'recorder_type': 'RX',
            'duration': 5.0,
            'start_time': '2026-02-19 12:00:00',
            'file_size': 480000,
            'timestamp': '2026-02-19T12:00:00',
            'recognized': False
        }

        record_id = await server.save_recording_async(recording)

        # 异步更新识别结果
        await server.update_recognition_async(
            filepath='test.wav',
            result={
                'text': 'CQ CQ CQ',
                'type': 'CQ',
                'confidence': 0.95,
                'rms_db': -20.0,
                'snr_db': 25.0
            }
        )

        # 批量处理
        recordings = [recording] * 10
        results = await server.batch_process_recordings(recordings)

        # 清理
        await server.cleanup()

    asyncio.run(main())


if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("异步优化集成示例")
    print("=" * 60)

    # 运行示例
    example_usage()

    print("\n" + "=" * 60)
    print("异步使用示例")
    print("=" * 60)

    example_async_usage()
