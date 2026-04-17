"""Logger configuration for AI Emoji API service."""
import sys
from pathlib import Path

from loguru import logger


def setup_logger(log_level: str = "INFO") -> logger:
    """Configure and return a loguru logger instance."""
    logger.remove()

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss} | "
        "{level: <8} | "
        "{name}:{function}:{line} - "
        "{message}"
    )

    logger.add(
        sys.stdout,
        format=console_format,
        level=log_level,
        colorize=True,
        enqueue=True,
    )

    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        format=file_format,
        level=log_level,
        rotation="1 day",
        retention="30 days",
        compression="zip",
        enqueue=True,
    )

    logger.add(
        log_dir / "error_{time:YYYY-MM-DD}.log",
        format=file_format,
        level="ERROR",
        rotation="1 day",
        retention="30 days",
        compression="zip",
        enqueue=True,
    )

    return logger
