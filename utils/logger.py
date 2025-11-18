import logging
import os
from logging.handlers import RotatingFileHandler

from .files import ensure_dir


_LOGGER_INITIALIZED = False


def setup_logging(log_dir: str = 'logs', level: int = logging.INFO) -> None:
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return
    ensure_dir(log_dir)
    log_path = os.path.join(log_dir, 'auto_ai_testing.log')

    logger = logging.getLogger()
    logger.setLevel(level)

    fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(name)s: %(message)s')

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    _LOGGER_INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)