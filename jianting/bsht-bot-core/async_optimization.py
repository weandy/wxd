"""
异步优化模块 - 渐进式改进

在保持现有多线程架构的基础上，优化关键路径：
1. 异步HTTP客户端 - 用于非gRPC的API调用
2. 线程池优化 - CPU密集型任务不阻塞主线程
3. 性能指标收集 - 监控关键指标

设计原则:
- 保持向后兼容
- 可逐步集成
- 低风险改进
"""

import asyncio
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional, Callable, Any, Dict, List
from functools import wraps
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ==================== 1. 性能指标收集 ====================

@dataclass
class PerformanceMetrics:
    """性能指标"""
    operation: str
    count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    errors: int = 0
    _samples: list = None  # 存储原始样本用于百分位计算

    def __post_init__(self):
        if self._samples is None:
            self._samples = []

    @property
    def avg_time(self) -> float:
        return self.total_time / self.count if self.count > 0 else 0

    @property
    def error_rate(self) -> float:
        return self.errors / self.count if self.count > 0 else 0

    def get_percentile(self, percentile: float) -> float:
        """获取百分位数 (0-100)"""
        if not self._samples:
            return 0.0
        sorted_samples = sorted(self._samples)
        index = int(len(sorted_samples) * percentile / 100)
        index = min(index, len(sorted_samples) - 1)
        return sorted_samples[index]

    @property
    def p50(self) -> float:
        """P50 (中位数)"""
        return self.get_percentile(50)

    @property
    def p95(self) -> float:
        """P95"""
        return self.get_percentile(95)

    @property
    def p99(self) -> float:
        """P99"""
        return self.get_percentile(99)


class MetricsCollector:
    """轻量级性能指标收集器"""

    def __init__(self, max_samples: int = 1000):
        """
        Args:
            max_samples: 每个操作保留的最大样本数 (用于百分位计算)
        """
        self._metrics: Dict[str, PerformanceMetrics] = {}
        self._lock = threading.Lock()
        self._max_samples = max_samples  # 限制内存使用

    def record(self, operation: str, duration: float, error: bool = False):
        """记录指标"""
        with self._lock:
            if operation not in self._metrics:
                self._metrics[operation] = PerformanceMetrics(operation=operation)

            m = self._metrics[operation]
            m.count += 1
            m.total_time += duration
            m.min_time = min(m.min_time, duration)
            m.max_time = max(m.max_time, duration)
            if error:
                m.errors += 1

            # 保留样本用于百分位计算
            if len(m._samples) < self._max_samples:
                m._samples.append(duration)

    def get_metrics(self, operation: str) -> Optional[PerformanceMetrics]:
        """获取指标"""
        with self._lock:
            return self._metrics.get(operation)

    def get_all_metrics(self) -> List[PerformanceMetrics]:
        """获取所有指标"""
        with self._lock:
            return list(self._metrics.values())

    def print_summary(self, show_percentiles: bool = True):
        """打印摘要

        Args:
            show_percentiles: 是否显示P50/P95/P99
        """
        print("\n" + "=" * 60)
        print("📊 性能指标摘要")
        print("=" * 60)
        for m in self.get_all_metrics():
            print(f"\n{m.operation}:")
            print(f"  次数: {m.count}")
            print(f"  平均: {m.avg_time*1000:.2f}ms")
            print(f"  最小: {m.min_time*1000:.2f}ms")
            print(f"  最大: {m.max_time*1000:.2f}ms")
            print(f"  错误: {m.errors} ({m.error_rate*100:.1f}%)")
            if show_percentiles and m.count > 0:
                print(f"  P50:  {m.p50*1000:.2f}ms")
                print(f"  P95:  {m.p95*1000:.2f}ms")
                print(f"  P99:  {m.p99*1000:.2f}ms")
        print("\n")

    def check_alerts(self, thresholds: Dict[str, float]) -> List[Dict]:
        """
        检查是否触发告警

        Args:
            thresholds: 阈值字典，格式: {"operation": threshold_ms}

        Returns:
            告警列表
        """
        alerts = []
        for m in self.get_all_metrics():
            if m.operation in thresholds:
                threshold_sec = thresholds[m.operation] / 1000  # 转换为秒
                if m.p95 > threshold_sec:
                    alerts.append({
                        "operation": m.operation,
                        "p95_ms": m.p95 * 1000,
                        "threshold_ms": thresholds[m.operation],
                        "severity": "critical" if m.p99 > threshold_sec else "warning"
                    })
        return alerts


# 全局指标收集器
_global_metrics = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标收集器"""
    return _global_metrics


# ==================== 2. 线程池优化 ====================

class ThreadPoolManager:
    """
    线程池管理器

    为不同类型的任务提供专门的线程池：
    - IO密集型: 网络请求、文件读写
    - CPU密集型: 音频处理、编解码
    """

    def __init__(self):
        # CPU密集型任务线程池
        self._cpu_pool = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="cpu_worker"
        )

        # IO密集型任务线程池
        self._io_pool = ThreadPoolExecutor(
            max_workers=8,
            thread_name_prefix="io_worker"
        )

        # 音频处理专用线程池
        self._audio_pool = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="audio_worker"
        )

        logger.info("线程池管理器初始化完成")

    def submit_cpu(self, fn: Callable, *args, **kwargs) -> Future:
        """提交CPU密集型任务"""
        return self._cpu_pool.submit(fn, *args, **kwargs)

    def submit_io(self, fn: Callable, *args, **kwargs) -> Future:
        """提交IO密集型任务"""
        return self._io_pool.submit(fn, *args, **kwargs)

    def submit_audio(self, fn: Callable, *args, **kwargs) -> Future:
        """提交音频处理任务"""
        return self._audio_pool.submit(fn, *args, **kwargs)

    def shutdown(self, wait: bool = True):
        """关闭所有线程池"""
        logger.info("关闭线程池...")
        self._cpu_pool.shutdown(wait=wait)
        self._io_pool.shutdown(wait=wait)
        self._audio_pool.shutdown(wait=wait)


# 全局线程池管理器
_global_pool_manager: Optional[ThreadPoolManager] = None
_pool_lock = threading.Lock()


def get_thread_pool() -> ThreadPoolManager:
    """获取全局线程池管理器"""
    global _global_pool_manager

    with _pool_lock:
        if _global_pool_manager is None:
            _global_pool_manager = ThreadPoolManager()
        return _global_pool_manager


# ==================== 3. 异步HTTP客户端 ====================

class AsyncHttpClient:
    """
    异步HTTP客户端

    用于非gRPC的HTTP API调用，如：
    - 微信推送
    - 外部 webhook
    - 健康检查
    """

    def __init__(self, timeout: float = 10.0):
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout = timeout

    async def _get_client(self) -> 'httpx.AsyncClient':
        """获取或创建异步客户端"""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                http2=True
            )
        return self._client

    async def get(self, url: str, **kwargs) -> Dict[str, Any]:
        """异步GET请求"""
        metrics = get_metrics_collector()
        start = time.time()

        try:
            client = await self._get_client()
            response = await client.get(url, **kwargs)
            duration = time.time() - start
            metrics.record("http.get", duration, error=response.status_code >= 400)

            return {
                "status_code": response.status_code,
                "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
            }
        except Exception as e:
            duration = time.time() - start
            metrics.record("http.get", duration, error=True)
            logger.error(f"HTTP GET失败: {url}, {e}")
            raise

    async def post(self, url: str, **kwargs) -> Dict[str, Any]:
        """异步POST请求"""
        metrics = get_metrics_collector()
        start = time.time()

        try:
            client = await self._get_client()
            response = await client.post(url, **kwargs)
            duration = time.time() - start
            metrics.record("http.post", duration, error=response.status_code >= 400)

            return {
                "status_code": response.status_code,
                "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
            }
        except Exception as e:
            duration = time.time() - start
            metrics.record("http.post", duration, error=True)
            logger.error(f"HTTP POST失败: {url}, {e}")
            raise

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None


# ==================== 4. 便捷装饰器 ====================

def timed_async(operation: str = ""):
    """异步函数计时装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            metrics = get_metrics_collector()
            start = time.time()
            error = False

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error = True
                raise
            finally:
                duration = time.time() - start
                op_name = operation or func.__name__
                metrics.record(op_name, duration, error=error)

        return wrapper
    return decorator


def timed_sync(operation: str = ""):
    """同步函数计时装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            metrics = get_metrics_collector()
            start = time.time()
            error = False

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = True
                raise
            finally:
                duration = time.time() - start
                op_name = operation or func.__name__
                metrics.record(op_name, duration, error=error)

        return wrapper
    return decorator


def run_in_pool(pool_type: str = "cpu"):
    """
    线程池执行装饰器

    Args:
        pool_type: "cpu", "io", 或 "audio"
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            pool = get_thread_pool()

            if pool_type == "cpu":
                return pool.submit_cpu(func, *args, **kwargs).result()
            elif pool_type == "io":
                return pool.submit_io(func, *args, **kwargs).result()
            elif pool_type == "audio":
                return pool.submit_audio(func, *args, **kwargs).result()
            else:
                return func(*args, **kwargs)

        return wrapper
    return decorator


# ==================== 5. 性能优化集成 ====================

class PerformanceOptimizer:
    """
    性能优化器 - 整合所有优化功能
    """

    def __init__(self):
        self.metrics = get_metrics_collector()
        self.pool = get_thread_pool()
        self._async_http: Optional[AsyncHttpClient] = None

    def get_async_http(self) -> AsyncHttpClient:
        """获取异步HTTP客户端"""
        if self._async_http is None:
            self._async_http = AsyncHttpClient()
        return self._async_http

    async def batch_process(self, items: List, processor: Callable, max_concurrency: int = 5) -> List:
        """
        并发批处理

        Args:
            items: 要处理的项目列表
            processor: 处理函数 (async)
            max_concurrency: 最大并发数

        Returns:
            处理结果列表
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def process_with_limit(item):
            async with semaphore:
                return await processor(item)

        tasks = [process_with_limit(item) for item in items]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def print_performance_report(self):
        """打印性能报告"""
        self.metrics.print_summary()

    async def cleanup(self):
        """清理资源"""
        if self._async_http:
            await self._async_http.close()
        self.pool.shutdown()


# 全局优化器
_global_optimizer: Optional[PerformanceOptimizer] = None


def get_optimizer() -> PerformanceOptimizer:
    """获取全局性能优化器"""
    global _global_optimizer

    if _global_optimizer is None:
        _global_optimizer = PerformanceOptimizer()

    return _global_optimizer


# ==================== 6. 使用示例 ====================

if __name__ == "__main__":
    # 示例1: 使用线程池处理CPU密集型任务
    def cpu_intensive_task(data):
        """模拟CPU密集型任务"""
        time.sleep(0.1)  # 模拟处理
        return f"处理完成: {data}"

    pool = get_thread_pool()
    result = pool.submit_cpu(cpu_intensive_task, "测试数据").result()
    print(f"结果: {result}")

    # 示例2: 使用异步HTTP客户端
    async def test_async_http():
        client = AsyncHttpClient()
        try:
            # 模拟请求
            print("异步HTTP客户端已准备")
        finally:
            await client.close()

    asyncio.run(test_async_http())

    # 示例3: 使用指标收集
    metrics = get_metrics_collector()
    metrics.record("test_operation", 0.05, error=False)
    metrics.record("test_operation", 0.03, error=False)
    metrics.record("test_operation", 0.10, error=True)

    metrics.print_summary()

    # 示例4: 使用装饰器
    @timed_sync("my_task")
    def my_task():
        time.sleep(0.01)
        return "完成"

    result = my_task()
    print(f"任务结果: {result}")

    print("\n✅ 异步优化模块测试完成")
