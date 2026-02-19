"""
统一的错误处理工具

提供一致的错误处理和日志记录方式，避免混用print和logger
"""

import logging
import sys
import traceback
import inspect
from typing import Optional, Callable, Any
from functools import wraps


class ErrorHandler:
    """统一的错误处理器"""

    def __init__(self, module_name: str):
        """
        初始化错误处理器

        Args:
            module_name: 模块名称，用于日志记录
        """
        self.logger = logging.getLogger(module_name)

    def handle_exception(self,
                        e: Exception,
                        context: str = "",
                        reraise: bool = False,
                        level: str = "ERROR") -> None:
        """
        统一异常处理

        Args:
            e: 异常对象
            context: 上下文信息
            reraise: 是否重新抛出异常
            level: 日志级别 (ERROR, WARNING, CRITICAL)
        """
        # 获取调用栈信息
        frame = inspect.currentframe()
        location = "unknown"
        if frame and frame.f_back:
            frame_info = inspect.getframeinfo(frame.f_back)
            location = f"{frame_info.filename}:{frame_info.lineno}"

        # 构建错误消息
        msg_parts = [
            f"[{location}]",
            f"{context or 'Error'}:"
        ]

        # 添加异常类型和消息
        msg_parts.append(f"{type(e).__name__}: {str(e)}")

        # 构建完整日志消息
        log_message = '\n'.join(msg_parts)

        # 获取堆栈跟踪
        stack_trace = ''.join(traceback.format_exception(
            type(e), e, e.__traceback__
        ))

        # 记录日志
        log_func = getattr(self.logger, level.lower(), self.logger.error)
        log_func(log_message)

        # 在debug级别记录完整堆栈
        if stack_trace:
            self.logger.debug(f"堆栈跟踪:\n{stack_trace}")

        # 重新抛出异常
        if reraise:
            raise

    @staticmethod
    def validate_not_empty(value: Any,
                          field_name: str,
                          module_name: str) -> None:
        """
        验证输入不为空

        Args:
            value: 要验证的值
            field_name: 字段名称
            module_name: 模块名称

        Raises:
            ValueError: 如果值为空
        """
        logger = logging.getLogger(module_name)

        if value is None:
            error_msg = f"{field_name} 不能为 None"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if isinstance(value, str) and not value.strip():
            error_msg = f"{field_name} 不能为空字符串"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
            error_msg = f"{field_name} 不能为空集合"
            logger.error(error_msg)
            raise ValueError(error_msg)

    @staticmethod
    def validate_range(value: float,
                      min_val: float,
                      max_val: float,
                      field_name: str,
                      module_name: str) -> None:
        """
        验证数值范围

        Args:
            value: 要验证的值
            min_val: 最小值
            max_val: 最大值
            field_name: 字段名称
            module_name: 模块名称

        Raises:
            ValueError: 如果值超出范围
        """
        logger = logging.getLogger(module_name)

        if not (min_val <= value <= max_val):
            error_msg = f"{field_name} 值 {value} 超出范围 [{min_val}, {max_val}]"
            logger.error(error_msg)
            raise ValueError(error_msg)


def log_errors(module_name: str = "",
               context: str = "",
               reraise: bool = False,
               level: str = "ERROR"):
    """
    错误日志装饰器

    自动记录函数中的异常到日志系统

    Args:
        module_name: 模块名称
        context: 上下文描述
        reraise: 是否重新抛出异常
        level: 日志级别

    Usage:
        @log_errors("my_module", "数据库操作")
        def save_data(data):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            handler = ErrorHandler(
                module_name or func.__module__,
            )

            try:
                return func(*args, **kwargs)
            except Exception as e:
                ctx = context or f"{func.__name__}({args}, {kwargs})"
                handler.handle_exception(e, context=ctx, reraise=reraise, level=level)

                if not reraise:
                    # 返回None或默认值
                    return None

        return wrapper
    return decorator


def safe_execute(default: Any = None,
                 log_module: str = "",
                 log_level: str = "WARNING"):
    """
    安全执行装饰器 - 返回默认值而不是抛出异常

    适用于可能失败但不影响主流程的操作

    Args:
        default: 发生异常时返回的默认值
        log_module: 模块名称
        log_level: 日志级别

    Usage:
        @safe_execute(default=[], log_module="audio")
        def get_audio_devices():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(log_module or func.__module__)
            log_func = getattr(logger, log_level.lower(), logger.warning)

            try:
                return func(*args, **kwargs)
            except Exception as e:
                log_func(f"{func.__name__} 执行失败: {e}")
                return default

        return wrapper
    return decorator


def retry_on_error(max_attempts: int = 3,
                   backoff: float = 1.0,
                   retry_on: tuple = (Exception,),
                   log_module: str = ""):
    """
    重试装饰器 - 失败时自动重试

    Args:
        max_attempts: 最大尝试次数
        backoff: 基础退避时间(秒)
        retry_on: 需要重试的异常类型
        log_module: 模块名称

    Usage:
        @retry_on_error(max_attempts=3, backoff=2.0)
        def fetch_api_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(log_module or func.__module__)
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    last_exception = e

                    if attempt < max_attempts - 1:
                        # 指数退避
                        wait_time = backoff * (2 ** attempt)
                        logger.warning(
                            f"{func.__name__} 失败 "
                            f"({attempt + 1}/{max_attempts}): {e}, "
                            f"{wait_time:.1f}秒后重试"
                        )
                        import time
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"{func.__name__} 重试次数用尽 "
                            f"({max_attempts}次): {e}"
                        )

            # 所有重试都失败
            raise last_exception

        return wrapper
    return decorator


# 便捷函数
def get_error_handler(module_name: str) -> ErrorHandler:
    """获取指定模块的错误处理器"""
    return ErrorHandler(module_name)


def setup_logger(name: str,
                 level: str = "INFO",
                 log_file: Optional[str] = None,
                 format_string: Optional[str] = None) -> logging.Logger:
    """
    设置标准化的日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别
        log_file: 日志文件路径 (可选)
        format_string: 日志格式 (可选)

    Returns:
        配置好的Logger对象
    """
    logger = logging.getLogger(name)

    # 避免重复添加handler
    if logger.handlers:
        return logger

    # 设置日志级别
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 默认格式
    if format_string is None:
        format_string = (
            '%(asctime)s - %(name)s - %(levelname)s - '
            '[%(filename)s:%(lineno)d] - %(message)s'
        )

    formatter = logging.Formatter(format_string)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器 (可选)
    if log_file:
        from pathlib import Path
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
