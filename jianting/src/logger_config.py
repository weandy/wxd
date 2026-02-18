"""
日志配置模块 - 统一管理日志输出
"""
import os
import logging
import logging.handlers
from datetime import datetime

# 创建logs目录
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# 日志文件配置
LOG_FILES = {
    "main": os.path.join(LOGS_DIR, "bot_server.log"),      # 主日志
    "recognize": os.path.join(LOGS_DIR, "recognize.log"),  # 识别日志
    "error": os.path.join(LOGS_DIR, "error.log"),          # 错误日志
}

# 日志格式 (结构化)
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 识别日志专用格式
RECOGNIZE_FORMAT = "%(asctime)s [%(levelname)s] [%(channel)s] [%(user)s] %(message)s"


def setup_logger(name: str = "BSHTBox", 
                log_file: str = None,
                level: int = logging.INFO,
                console: bool = True) -> logging.Logger:
    """
    创建日志器
    
    Args:
        name: 日志器名称
        log_file: 日志文件名 (main/recognize/error)
        level: 日志级别
        console: 是否输出到控制台
        
    Returns:
        Logger实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()  # 避免重复添加
    
    # 文件handler - 按时间轮转，每周一个新文件
    if log_file:
        file_path = LOG_FILES.get(log_file, log_file)
        
        # TimeRotatingFileHandler: 每天午夜轮转，保留7天
        file_handler = logging.handlers.TimedRotatingFileHandler(
            file_path,
            when="midnight",      # 每天午夜
            interval=1,           # 每天一个文件
            backupCount=7,        # 保留7天
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(file_handler)
    
    # 控制台handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        # 控制台用简化格式
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", 
            DATE_FORMAT
        ))
        logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str, log_file: str = "main") -> logging.Logger:
    """获取已配置的日志器"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        # 首次获取时配置
        if log_file == "recognize":
            return setup_logger(name, "recognize")
        elif log_file == "error":
            return setup_logger(name, "error")
        else:
            return setup_logger(name, "main")
    return logger


# 预配置的日志器
main_logger = setup_logger("BSHTBox", "main")
recognize_logger = setup_logger("Recognizer", "recognize")
error_logger = setup_logger("Error", "error")
