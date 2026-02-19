# 监控告警系统详细方案

> 优化目标: 提升可观测性和运维效率
> 实施难度: 中等
> 预期工期: 1周

---

## 📋 目录

1. [监控体系架构](#监控体系架构)
2. [核心组件实现](#核心组件实现)
3. [告警规则配置](#告警规则配置)
4. [可视化仪表板](#可视化仪表板)
5. [部署和使用](#部署和使用)

---

## 🏗️ 监控体系架构

### 整体架构图

```
┌──────────────────────────────────────────────────────────┐
│                    监控告警系统                           │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │          数据采集层 (Metrics Collection)         │    │
│  ├────────────────────────────────────────────────┤    │
│  │                                                │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐    │    │
│  │  │ Application│  │ System   │  │ Business │    │    │
│  │  │   Metrics │  │ Metrics  │  │ Metrics  │    │    │
│  │  └─────┬────┘  └─────┬────┘  └─────┬────┘    │    │
│  └────────┼─────────────┼─────────────┼──────────┘    │
│           │             │             │               │
│  ┌────────▼─────────────▼─────────────▼──────────┐    │
│  │            MetricsCollector (收集器)           │    │
│  │        - In-memory (内存)                     │    │
│  │        - Redis (可选，持久化)                  │    │
│  └───────────────────────────┬────────────────────┘    │
│                              │                          │
│  ┌───────────────────────────▼────────────────────┐   │
│  │         MetricsProcessor (处理器)              │   │
│  │  - 聚合 (Aggregation)                          │   │
│  │  - 计算 (P50, P95, P99)                        │   │
│  │  - 趋势 (Trend analysis)                       │   │
│  └───────────────────────────┬────────────────────┘   │
│                              │                          │
│           ┌──────────────────┼──────────────────┐      │
│           │                  │                  │      │
│  ┌────────▼────────┐  ┌──────▼────────┐  ┌───▼────────┐│
│  │  Prometheus    │  │   Logging     │  │  Alerting  ││
│  │  (时序数据库)    │  │   (日志)      │  │  (告警)    ││
│  └─────────────────┘  └───────────────┘  └────────────┘│
│                                                            │
└────────────────────────────────────────────────────────┘
```

### 三层监控体系

#### 1. 应用层监控 (Application Metrics)

**监控指标**:
- 音频处理延迟
- 识别成功率
- API调用成功率
- 数据库查询性能
- 内存/CPU使用率

**采集方式**:
```python
# 装饰器自动采集
@timed("audio_decode")
def decode_audio(data):
    ...

# 手动记录
metrics.record("user_active", 1, tags={"user_id": 123})
```

#### 2. 系统层监控 (System Metrics)

**监控指标**:
- CPU使用率
- 内存使用率
- 磁盘I/O
- 网络I/O
- 文件描述符数量

**采集方式**:
```python
import psutil

def collect_system_metrics():
    return {
        'cpu_percent': psutil.cpu_percent(),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_usage': psutil.disk_usage('/').percent,
        'network_io': psutil.net_io_counters()
    }
```

#### 3. 业务层监控 (Business Metrics)

**监控指标**:
- 每日录音数量
- 识别准确率
- 信号类型分布
- 用户活跃度
- 推送成功率

**采集方式**:
```python
# 业务事件记录
metrics.record("recording_created", 1, tags={
    "channel_id": 12345,
    "user_id": 67890
})
```

---

## 💻 核心组件实现

### 1. 指标收集器

```python
# monitoring/metrics_collector.py - 新建文件
import time
import threading
from typing import Dict, List, Optional, Any
from collections import deque
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class Metric:
    """单个指标数据点"""
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricStats:
    """指标统计信息"""
    name: str
    count: int = 0
    min: float = float('inf')
    max: float = float('-inf')
    sum: float = 0.0
    avg: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """指标收集器

    特性:
    - 内存存储 (可选择Redis持久化)
    - 滑动窗口统计
  - 百分位数计算 (P50, P95, P99)
    - 多维度标签支持
    """

    def __init__(self, window_size: int = 1000, ttl: int = 3600):
        """
        Args:
            window_size: 滑动窗口大小
            ttl: 数据生存时间(秒)
        """
        self.window_size = window_size
        self.ttl = ttl

        # 指标存储: {metric_key: deque(values)}
        self._metrics: Dict[str, deque] = {}
        self._lock = threading.Lock()

        # 标签索引
        self._tags_index: Dict[str, List[str]] = {}

    def record(self, name: str, value: float, tags: Optional[Dict] = None):
        """记录指标

        Args:
            name: 指标名称
            value: 指标值
            tags: 标签 (用于分组和过滤)
        """
        timestamp = time.time()
        tags = tags or {}

        # 生成metric key (包含标签)
        tag_str = ','.join(f"{k}={v}" for k, v in sorted(tags.items()))
        metric_key = f"{name}:{tag_str}" if tag_str else name

        with self._lock:
            # 创建或获取deque
            if metric_key not in self._metrics:
                self._metrics[metric_key] = deque(maxlen=self.window_size)
                self._tags_index[name] = self._tags_index.get(name, [])
                self._tags_index[name].append(metric_key)

            # 添加数据点
            self._metrics[metric_key].append(
                Metric(name, value, timestamp, tags)
            )

            # 清理过期数据
            self._cleanup_old_data(metric_key)

    def _cleanup_old_data(self, metric_key: str):
        """清理过期数据"""
        if metric_key not in self._metrics:
            return

        metrics_deque = self._metrics[metric_key]
        now = time.time()

        # 移除过期数据
        while metrics_deque and now - metrics_deque[0].timestamp > self.ttl:
            metrics_deque.popleft()

    def get_stats(self, name: str, tags: Optional[Dict] = None) -> MetricStats:
        """获取统计信息

        Args:
            name: 指标名称
            tags: 标签过滤

        Returns:
            统计信息对象
        """
        with self._lock:
            # 获取匹配的metric keys
            metric_keys = self._tags_index.get(name, [])

            if tags:
                # 过滤匹配标签的metrics
                tag_str = ','.join(f"{k}={v}" for k, v in sorted(tags.items()))
                metric_keys = [k for k in metric_keys if tag_str in k]

            if not metric_keys:
                return MetricStats(name=name)

            # 合并所有匹配的数据
            all_values = []
            for key in metric_keys:
                if key in self._metrics:
                    all_values.extend([m.value for m in self._metrics[key]])

            if not all_values:
                return MetricStats(name=name)

            # 计算统计信息
            all_values.sort()

            return MetricStats(
                name=name,
                count=len(all_values),
                min=min(all_values),
                max=max(all_values),
                sum=sum(all_values),
                avg=sum(all_values) / len(all_values),
                p50=all_values[len(all_values) // 2],
                p95=all_values[int(len(all_values) * 0.95)] if len(all_values) > 20 else all_values[-1],
                p99=all_values[int(len(all_values) * 0.99)] if len(all_values) > 100 else all_values[-1],
                tags=tags or {}
            )

    def get_all_metrics(self) -> List[MetricStats]:
        """获取所有指标的统计"""
        with self._lock:
            return [
                self.get_stats(name)
                for name in self._tags_index.keys()
            ]

    def get_recent(self, name: str, count: int = 10, tags: Optional[Dict] = None) -> List[Metric]:
        """获取最近的数据点"""
        with self._lock:
            metric_keys = self._tags_index.get(name, [])

            if tags:
                tag_str = ','.join(f"{k}={v}" for k, v in sorted(tags.items()))
                metric_keys = [k for k in metric_keys if tag_str in k]

            # 获取最近的数据
            all_metrics = []
            for key in metric_keys:
                if key in self._metrics:
                    all_metrics.extend(list(self._metrics[key])[-count:])

            # 按时间排序
            all_metrics.sort(key=lambda m: m.timestamp, reverse=True)

            return all_metrics[:count]

    def clear(self):
        """清空所有指标"""
        with self._lock:
            self._metrics.clear()
            self._tags_index.clear()


# 全局单例
_global_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标收集器"""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector
```

### 2. 计时装饰器

```python
# monitoring/decorators.py - 新建文件
import time
import functools
from typing import Callable, Optional
from .metrics_collector import get_metrics_collector
import logging

logger = logging.getLogger(__name__)


def timed(metric_name: str, tags: Optional[dict] = None):
    """计时装饰器

    Usage:
        @timed("audio_process", {"codec": "opus"})
        def process_audio(data):
            ...

    Args:
        metric_name: 指标名称
        tags: 标签
    """
    collector = get_metrics_collector()

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                collector.record(
                    f"{metric_name}.duration",
                    duration,
                    tags or {}
                )
        return wrapper
    return decorator


def counted(metric_name: str, tags: Optional[dict] = None):
    """计数装饰器

    Usage:
        @counted("api_calls", {"endpoint": "/login"})
        def login():
            ...

    Args:
        metric_name: 指标名称
        tags: 标签
    """
    collector = get_metrics_collector()

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                collector.record(
                    f"{metric_name}.success",
                    1,
                    tags or {}
                )
                return result
            except Exception as e:
                collector.record(
                    f"{metric_name}.error",
                    1,
                    {**(tags or {}), "error": type(e).__name__}
                )
                raise

        return wrapper
    return decorator


def gauge(metric_name: str, value_func: Callable, tags: Optional[dict] = None):
    """仪表盘装饰器 - 记录函数返回值

    Usage:
        @gauge("queue_size", lambda self: len(self.queue))
        def process(self):
            ...

    Args:
        metric_name: 指标名称
        value_func: 值函数
        tags: 标签
    """
    collector = get_metrics_collector()

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # 记录仪表盘值
            try:
                value = value_func(result)
                collector.record(metric_name, value, tags or {})
            except Exception as e:
                logger.warning(f"记录仪表盘失败: {e}")

            return result

        return wrapper
    return decorator
```

### 3. 告警规则引擎

```python
# monitoring/alerting.py - 新建文件
import asyncio
import logging
from typing import List, Callable, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import time

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """告警事件"""
    rule_name: str
    severity: AlertSeverity
    message: str
    current_value: float
    threshold: float
    tags: Dict[str, str]
    timestamp: float = field(default_factory=time.time)


class AlertRule:
    """告警规则"""

    def __init__(
        self,
        name: str,
        metric_name: str,
        condition: str,  # "gt", "lt", "eq", "gte", "lte"
        threshold: float,
        severity: AlertSeverity = AlertSeverity.WARNING,
        duration: int = 60,  # 持续时间(秒)
        tags: Optional[Dict] = None,
        message_template: Optional[str] = None
    ):
        """
        Args:
            name: 规则名称
            metric_name: 监控指标名称
            condition: 条件 (gt=大于, lt=小于, gte=大于等于, lte=小于等于)
            threshold: 阈值
            severity: 告警级别
            duration: 持续时间 (超过阈值多久才告警)
            tags: 标签过滤
            message_template: 消息模板
        """
        self.name = name
        self.metric_name = metric_name
        self.condition = condition
        self.threshold = threshold
        self.severity = severity
        self.duration = duration
        self.tags = tags or {}
        self.message_template = message_template or f"{name}: {metric_name} {condition} {threshold}"

        # 状态跟踪
        self._violation_start_time: Optional[float] = None
        self._last_alert_time: float = 0
        self._alert_cooldown = 300  # 告警冷却时间(秒)

    def evaluate(self, stats) -> Optional[Alert]:
        """评估规则

        Args:
            stats: MetricStats对象

        Returns:
            如果应该告警则返回Alert对象，否则返回None
        """
        # 获取对应的值
        if self.condition == "gt":
            current_value = stats.max
            violated = current_value > self.threshold
        elif self.condition == "lt":
            current_value = stats.min
            violated = current_value < self.threshold
        elif self.condition == "gte":
            current_value = stats.max
            violated = current_value >= self.threshold
        elif self.condition == "lte":
            current_value = stats.min
            violated = current_value <= self.threshold
        else:
            logger.warning(f"未知的条件: {self.condition}")
            return None

        now = time.time()

        if violated:
            # 检查是否已开始违规
            if self._violation_start_time is None:
                self._violation_start_time = now
                return None  # 刚开始违规，不立即告警

            # 检查是否超过持续时间
            if now - self._violation_start_time >= self.duration:
                # 检查冷却时间
                if now - self._last_alert_time < self._alert_cooldown:
                    return None  # 冷却中，不重复告警

                # 触发告警
                self._last_alert_time = now
                return Alert(
                    rule_name=self.name,
                    severity=self.severity,
                    message=self.message_template.format(
                        metric=self.metric_name,
                        value=current_value,
                        threshold=self.threshold
                    ),
                    current_value=current_value,
                    threshold=self.threshold,
                    tags=stats.tags
                )
        else:
            # 未违规，重置
            self._violation_start_time = None

        return None


class AlertManager:
    """告警管理器"""

    def __init__(self):
        self.rules: List[AlertRule] = []
        self._handlers: List[Callable[[Alert], None]] = []
        self._running = False

    def add_rule(self, rule: AlertRule):
        """添加告警规则"""
        self.rules.append(rule)
        logger.info(f"添加告警规则: {rule.name}")

    def add_handler(self, handler: Callable[[Alert], None]):
        """添加告警处理器"""
        self._handlers.append(handler)

    def evaluate_rules(self, stats_list: List):
        """评估所有规则"""
        for stats in stats_list:
            for rule in self.rules:
                # 只评估匹配的指标
                if rule.metric_name != stats.name:
                    continue

                # 检查标签匹配
                if rule.tags:
                    if not all(stats.tags.get(k) == v for k, v in rule.tags.items()):
                        continue

                # 评估规则
                alert = rule.evaluate(stats)
                if alert:
                    self._fire_alert(alert)

    def _fire_alert(self, alert: Alert):
        """触发告警"""
        logger.warning(f"🚨 告警: [{alert.severity.value.upper()}] {alert.message}")

        # 调用所有处理器
        for handler in self._handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"告警处理器失败: {e}")


# 预定义的告警处理器
def log_alert_handler(alert: Alert):
    """日志告警处理器"""
    logger.warning(
        f"告警触发: {alert.rule_name}",
        extra={
            'severity': alert.severity.value,
            'current_value': alert.current_value,
            'threshold': alert.threshold,
            'tags': alert.tags
        }
    )


def webhook_alert_handler(webhook_url: str):
    """Webhook告警处理器工厂"""
    import requests

    def handler(alert: Alert):
        try:
            response = requests.post(
                webhook_url,
                json={
                    'rule_name': alert.rule_name,
                    'severity': alert.severity.value,
                    'message': alert.message,
                    'current_value': alert.current_value,
                    'threshold': alert.threshold,
                    'tags': alert.tags,
                    'timestamp': alert.timestamp
                },
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Webhook告警发送成功: {alert.rule_name}")

        except Exception as e:
            logger.error(f"Webhook告警发送失败: {e}")

    return handler


def email_alert_handler(smtp_config: dict, recipients: List[str]):
    """邮件告警处理器工厂"""
    import smtplib
    from email.mime.text import MIMEText

    def handler(alert: Alert):
        try:
            # 构建邮件
            msg = MIMEText(
                f"告警详情:\n\n"
                f"规则: {alert.rule_name}\n"
                f"级别: {alert.severity.value}\n"
                f"消息: {alert.message}\n"
                f"当前值: {alert.current_value}\n"
                f"阈值: {alert.threshold}\n"
                f"标签: {alert.tags}\n"
                f"时间: {time.ctime(alert.timestamp)}"
            )

            msg['Subject'] = f"[{alert.severity.value.upper()}] {alert.rule_name}"
            msg['From'] = smtp_config['from']
            msg['To'] = ', '.join(recipients)

            # 发送
            with smtplib.SMTP(smtp_config['host'], smtp_config['port']) as server:
                if 'username' in smtp_config:
                    server.login(smtp_config['username'], smtp_config['password'])
                server.send_message(msg)

            logger.info(f"邮件告警发送成功: {alert.rule_name}")

        except Exception as e:
            logger.error(f"邮件告警发送失败: {e}")

    return handler
```

### 4. 监控服务

```python
# monitoring/monitoring_service.py - 新建文件
import asyncio
import logging
from typing import List
from .metrics_collector import MetricsCollector, get_metrics_collector
from .alerting import AlertManager, AlertRule, AlertSeverity
import psutil

logger = logging.getLogger(__name__)


class MonitoringService:
    """监控服务

    职责:
    - 定期采集系统指标
    - 评估告警规则
    - 发送告警通知
    """

    def __init__(self, collector: MetricsCollector = None):
        """
        Args:
            collector: 指标收集器，如果不提供则使用全局单例
        """
        self.collector = collector or get_metrics_collector()
        self.alert_manager = AlertManager()
        self._running = False
        self._tasks: List[asyncio.Task] = []

        # 添加默认告警处理器
        self.alert_manager.add_handler(log_alert_handler)

    def setup_default_rules(self):
        """设置默认告警规则"""
        rules = [
            # CPU使用率告警
            AlertRule(
                name="high_cpu_usage",
                metric_name="system.cpu.percent",
                condition="gt",
                threshold=80.0,
                severity=AlertSeverity.WARNING,
                duration=300  # 持续5分钟
            ),

            # 内存使用率告警
            AlertRule(
                name="high_memory_usage",
                metric_name="system.memory.percent",
                condition="gt",
                threshold=85.0,
                severity=AlertSeverity.ERROR,
                duration=300
            ),

            # 磁盘使用率告警
            AlertRule(
                name="high_disk_usage",
                metric_name="system.disk.percent",
                condition="gt",
                threshold=90.0,
                severity=AlertSeverity.CRITICAL,
                duration=600  # 持续10分钟
            ),

            # 音频处理延迟告警
            AlertRule(
                name="slow_audio_processing",
                metric_name="audio_process.duration",
                condition="gt",
                threshold=0.1,  # 100ms
                severity=AlertSeverity.WARNING,
                duration=60
            ),

            # API错误率告警
            AlertRule(
                name="high_api_error_rate",
                metric_name="api_calls.error",
                condition="gt",
                threshold=10.0,  # 每分钟超过10次错误
                severity=AlertSeverity.ERROR,
                duration=60
            ),

            # 数据库查询延迟告警
            AlertRule(
                name="slow_database_query",
                metric_name="database.query.duration",
                condition="gt",
                threshold=1.0,  # 1秒
                severity=AlertSeverity.WARNING,
                duration=60
            ),
        ]

        for rule in rules:
            self.alert_manager.add_rule(rule)

        logger.info(f"已加载 {len(rules)} 个告警规则")

    async def start(self, interval: int = 10):
        """启动监控服务

        Args:
            interval: 采集间隔(秒)
        """
        self._running = True

        logger.info("🔍 监控服务启动")

        # 启动采集任务
        self._tasks = [
            asyncio.create_task(self._collect_system_metrics(interval)),
            asyncio.create_task(self._evaluate_alerts(interval)),
        ]

    async def stop(self):
        """停止监控服务"""
        logger.info("🛑 监控服务停止")
        self._running = False

        # 取消所有任务
        for task in self._tasks:
            task.cancel()

        # 等待任务结束
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _collect_system_metrics(self, interval: int):
        """采集系统指标"""
        while self._running:
            try:
                # CPU使用率
                cpu_percent = psutil.cpu_percent(interval=1)
                self.collector.record("system.cpu.percent", cpu_percent)

                # 内存使用率
                memory = psutil.virtual_memory()
                self.collector.record("system.memory.percent", memory.percent)
                self.collector.record("system.memory.available", memory.available)

                # 磁盘使用率
                disk = psutil.disk_usage('/')
                self.collector.record("system.disk.percent", disk.percent)
                self.collector.record("system.disk.free", disk.free)

                # 网络I/O
                net_io = psutil.net_io_counters()
                self.collector.record("system.network.bytes_sent", net_io.bytes_sent)
                self.collector.record("system.network.bytes_recv", net_io.bytes_recv)

                logger.debug("系统指标采集完成")

            except Exception as e:
                logger.error(f"采集系统指标失败: {e}")

            await asyncio.sleep(interval)

    async def _evaluate_alerts(self, interval: int):
        """评估告警规则"""
        while self._running:
            try:
                # 获取所有指标统计
                all_stats = self.collector.get_all_metrics()

                # 评估规则
                self.alert_manager.evaluate_rules(all_stats)

            except Exception as e:
                logger.error(f"评估告警失败: {e}")

            await asyncio.sleep(interval)


# 使用示例
async def main():
    # 创建监控服务
    monitoring = MonitoringService()
    monitoring.setup_default_rules()

    # 添加告警处理器
    # monitoring.alert_manager.add_handler(
    #     webhook_alert_handler("https://hooks.example.com/alert")
    # )

    # 启动监控
    await monitoring.start(interval=10)

    try:
        # 运行...
        await asyncio.sleep(3600)
    finally:
        await monitoring.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

---

## 📊 可视化仪表板

### Grafana仪表板配置

```json
{
  "dashboard": {
    "title": "BSHT Bot 监控",
    "panels": [
      {
        "title": "系统资源使用率",
        "type": "graph",
        "targets": [
          {
            "expr": "system_cpu_percent",
            "legendFormat": "CPU {{percent}}"
          },
          {
            "expr": "system_memory_percent",
            "legendFormat": "Memory {{percent}}"
          },
          {
            "expr": "system_disk_percent",
            "legendFormat": "Disk {{percent}}"
          }
        ]
      },
      {
        "title": "音频处理性能",
        "type": "graph",
        "targets": [
          {
            "expr": "audio_process_duration_p95",
            "legendFormat": "P95延迟 {{seconds}}"
          },
          {
            "expr": "audio_process_duration_p99",
            "legendFormat": "P99延迟 {{seconds}}"
          }
        ]
      },
      {
        "title": "API调用统计",
        "type": "stat",
        "targets": [
          {
            "expr": "api_calls_success",
            "legendFormat": "成功 {{count}}"
          },
          {
            "expr": "api_calls_error",
            "legendFormat": "失败 {{count}}"
          }
        ]
      },
      {
        "title": "识别准确率",
        "type": "gauge",
        "targets": [
          {
            "expr": "recognition_accuracy",
            "legendFormat": "{{percent}}%"
          }
        ]
      }
    ]
  }
}
```

### 简单的Web仪表板

```python
# monitoring/dashboard.py - 新建文件
from flask import Flask, render_template, jsonify
from .metrics_collector import get_metrics_collector
import logging

logger = logging.getLogger(__name__)

app = Flask(__name__)
collector = get_metrics_collector()


@app.route('/')
def index():
    """仪表板首页"""
    return render_template('dashboard.html')


@app.route('/api/metrics')
def api_metrics():
    """获取所有指标"""
    stats_list = collector.get_all_metrics()

    # 转换为JSON格式
    result = []
    for stats in stats_list:
        result.append({
            'name': stats.name,
            'count': stats.count,
            'min': stats.min,
            'max': stats.max,
            'avg': stats.avg,
            'p50': stats.p50,
            'p95': stats.p95,
            'p99': stats.p99,
            'tags': stats.tags
        })

    return jsonify(result)


@app.route('/api/metrics/<name>')
def api_metric_detail(name: str):
    """获取指标详情"""
    stats = collector.get_stats(name)

    if not stats.count:
        return jsonify({'error': '指标不存在'}), 404

    recent = collector.get_recent(name, count=20)

    return jsonify({
        'stats': {
            'name': stats.name,
            'count': stats.count,
            'min': stats.min,
            'max': stats.max,
            'avg': stats.avg,
            'p50': stats.p50,
            'p95': stats.p95,
            'p99': stats.p99,
            'tags': stats.tags
        },
        'recent': [
            {
                'value': m.value,
                'timestamp': m.timestamp
            }
            for m in recent
        ]
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
```

---

## 🚀 部署和使用

### 集成到现有代码

```python
# bot_server.py - 集成监控
from monitoring.metrics_collector import get_metrics_collector
from monitoring.decorators import timed, counted
from monitoring.monitoring_service import MonitoringService

class BotServer:
    def __init__(self, config):
        # ... 现有代码 ...

        # 初始化监控
        self.metrics = get_metrics_collector()
        self.monitoring = MonitoringService(self.metrics)
        self.monitoring.setup_default_rules()

    async def start(self):
        # ... 启动现有服务 ...

        # 启动监控服务
        await self.monitoring.start(interval=10)

    @timed("audio.packet_process", {"codec": "opus"})
    def _process_audio_packet(self, data: bytes, addr: tuple):
        """处理音频包 (带监控)"""
        # 现有处理逻辑...
        pass

    @counted("api.login")
    def login(self, username: str, password: str):
        """登录 (带监控)"""
        # 现有登录逻辑...
        pass
```

### Docker部署

```yaml
# docker-compose.yml - 添加监控服务
version: '3.8'

services:
  bsht-bot:
    build: .
    environment:
      - MONITORING_ENABLED=true
    ports:
      - "8080:8080"  # 监控面板

  # Prometheus - 时序数据库
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  # Grafana - 可视化
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

  # AlertManager - 告警管理
  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml
```

---

## 📈 预期效果

### 运维效率提升

**优化前**:
```
问题发现: 用户反馈 → 查看日志 → 分析原因
平均耗时: 30-60分钟

问题定位: 手动检查各个组件
平均耗时: 1-2小时
```

**优化后**:
```
问题发现: 实时告警 → 仪表板查看
平均耗时: 1-5分钟

问题定位: 查看指标趋势和关联
平均耗时: 10-30分钟

效率提升: 6-12倍
```

### 系统可靠性提升

- **预防性监控**: 在问题影响用户前发现
- **快速响应**: 告警后5分钟内响应
- **趋势分析**: 预测潜在问题
- **容量规划**: 基于数据决策

---

**预期收益**: 可观测性提升 10倍
**实施难度**: 中等
**推荐优先级**: 🔥 高优先级
