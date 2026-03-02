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


class WindowsSafeRotator:
    """Windows安全的文件轮转处理器 - 解决文件锁定问题"""

    def __init__(self, baseFilename, backupCount):
        self.baseFilename = baseFilename
        self.backupCount = backupCount
        self._file_locked_error_logged = False

    def __call__(self, stream):
        """执行轮转操作"""
        stream.close()

        # 获取带日期的备份文件名
        import glob
        base = self.baseFilename
        if os.path.exists(base):
            # 检查是否已有带日期的备份
            pattern = base + ".*"
            existing = glob.glob(pattern)

            if existing:
                # 已存在轮转文件，跳过
                return

            # 尝试重命名
            try:
                from datetime import datetime
                date_str = datetime.now().strftime("%Y-%m-%d")
                new_name = f"{base}.{date_str}"

                # 如果目标文件已存在，先删除（Windows需要）
                if os.path.exists(new_name):
                    try:
                        os.remove(new_name)
                    except PermissionError:
                        # 文件被锁定，静默跳过
                        if not self._file_locked_error_logged:
                            logging.warning(f"日志轮转: 文件 {new_name} 被锁定，跳过重命名")
                            self._file_locked_error_logged = True
                        return

                os.rename(base, new_name)
                self._file_locked_error_logged = False

            except PermissionError as e:
                # Windows 文件锁定 - 静默处理，下次重试
                if not self._file_locked_error_logged:
                    logging.warning(f"日志轮转: 文件被锁定，将在下个周期重试: {e}")
                    self._file_locked_error_logged = True
            except Exception as e:
                logging.warning(f"日志轮转失败: {e}")

        # 重新打开原文件
        try:
            stream.baseStream = open(self.baseFilename, 'a', encoding='utf-8')
        except Exception:
            pass  # 忽略打开失败


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
        # 添加 delay=True 避免启动时就打开文件
        # 添加 rbtHandler 处理轮转错误
        file_handler = logging.handlers.TimedRotatingFileHandler(
            file_path,
            when="midnight",      # 每天午夜
            interval=1,           # 每天一个文件
            backupCount=7,        # 保留7天
            encoding="utf-8",
            delay=True            # Windows 友好：延迟打开文件
        )

        # 处理 Windows 文件锁定错误
        def safe_rotator(*args):
            """安全的轮转处理，捕获 Windows 文件锁定错误
            兼容 Python 3.12+ (传递 source, dest 两个参数) 和旧版本 (传递 stream 一个参数)
            """
            # Python 3.12+ 传递两个参数: source, dest
            # 旧版本传递一个参数: stream
            if len(args) == 2:
                source, dest = args
                stream = None  # 新版本不需要手动关闭 stream
            else:
                stream = args[0] if args else None

            try:
                # 先关闭流
                if stream:
                    stream.close()
                # 尝试重命名
                from datetime import datetime
                date_str = datetime.now().strftime("%Y-%m-%d")
                new_name = f"{file_path}.{date_str}"

                # 如果目标文件已存在，跳过
                if os.path.exists(new_name):
                    return

                # 尝试移动文件
                if os.path.exists(file_path):
                    try:
                        os.rename(file_path, new_name)
                    except PermissionError:
                        # 文件被锁定，跳过轮转，下次重试
                        logging.debug(f"日志文件被锁定，轮转延迟")
                        return
            except Exception as e:
                logging.debug(f"日志轮转处理: {e}")

            # 重新打开文件
            try:
                stream.baseStream = open(file_path, 'a', encoding='utf-8')
            except Exception:
                pass

        file_handler.rotator = safe_rotator
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
