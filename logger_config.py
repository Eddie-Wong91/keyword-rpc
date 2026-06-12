import logging
import os
from concurrent_log_handler import ConcurrentRotatingFileHandler as _RotatingHandler
from config import LOG_DIR

_LOG_DIR = str(LOG_DIR)

def setup_logger(name=None, log_file='app.log', level=logging.INFO):
    """
    统一的日志配置函数

    Args:
        name: logger 名称,None 表示 root logger
        log_file: 日志文件名
        level: 日志级别

    Returns:
        logger 对象
    """
    logger = logging.getLogger(name)

    # 进程内幂等:同一 logger 名重复调用不再重复挂 handler
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    os.makedirs(_LOG_DIR, exist_ok=True)
    log_path = os.path.join(_LOG_DIR, log_file)

    # 文件 handler
    file_handler = _RotatingHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setLevel(level)

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)

    # 统一的日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
