"""Logger utility."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from ..config import LOG_LEVEL, LOG_FORMAT, LOG_JSON


class _JSONFormatter(logging.Formatter):
    """Один лог-запис -> один рядок JSON. Вмикається LOG_JSON=true."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class LoggerFactory:
    """Factory для створення налаштованих логерів."""

    _loggers: dict = {}

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """
        Отримати або створити логер.

        Args:
            name: Ім'я логера (зазвичай __name__)

        Returns:
            Налаштований логер
        """
        if name in LoggerFactory._loggers:
            return LoggerFactory._loggers[name]

        logger = logging.getLogger(name)

        # Уникнути дублювання обробників
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = _JSONFormatter() if LOG_JSON else logging.Formatter(LOG_FORMAT)
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(LOG_LEVEL)

        LoggerFactory._loggers[name] = logger
        return logger


def get_logger(name: str) -> logging.Logger:
    """Зручна функція для отримання логера."""
    return LoggerFactory.get_logger(name)
