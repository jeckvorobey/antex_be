"""Централизованная настройка логирования backend."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_MANAGED_HANDLER_ATTR = "_antex_managed_handler"
_LOGGING_CONFIG_ATTR = "_antex_logging_config"


class HealthcheckAccessFilter(logging.Filter):
    """Фильтрует access-log healthcheck, не затрагивая бизнес-логи."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Возвращает False только для uvicorn access-записей `/health`."""
        return "/health" not in record.getMessage()


def configure_logging(
    *,
    log_dir: str,
    log_level: str,
    log_file_max_bytes: int = 10 * 1024 * 1024,
    log_file_backup_count: int = 5,
    disable_file_logging: bool | None = None,
) -> None:
    """Настраивает console logging и warning/error file logging без дублей."""
    root_logger = logging.getLogger()
    level = _resolve_level(log_level)
    file_logging_disabled = _is_file_logging_disabled_for_context(disable_file_logging)
    root_logger.setLevel(level)
    config_fingerprint = (
        str(Path(log_dir)),
        level,
        log_file_max_bytes,
        log_file_backup_count,
        file_logging_disabled,
    )
    if getattr(root_logger, _LOGGING_CONFIG_ATTR, None) == config_fingerprint and any(
        getattr(handler, _MANAGED_HANDLER_ATTR, False) for handler in root_logger.handlers
    ):
        _configure_external_loggers(level)
        return

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _remove_managed_handlers(root_logger)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    _mark_managed(console_handler)
    root_logger.addHandler(console_handler)

    if not file_logging_disabled:
        file_handler = _build_file_handler(
            log_dir=log_dir,
            formatter=formatter,
            log_file_max_bytes=log_file_max_bytes,
            log_file_backup_count=log_file_backup_count,
        )
        if file_handler is not None:
            root_logger.addHandler(file_handler)

    _configure_external_loggers(level)
    setattr(root_logger, _LOGGING_CONFIG_ATTR, config_fingerprint)


def _resolve_level(log_level: str) -> int:
    """Преобразует строковый уровень логирования в значение logging."""
    return getattr(logging, log_level.upper(), logging.INFO)


def _is_file_logging_disabled_for_context(disable_file_logging: bool | None) -> bool:
    """Определяет, нужно ли отключить file handler для текущего процесса."""
    if disable_file_logging is not None:
        return disable_file_logging
    if os.environ.get("ANTEX_ENABLE_TEST_FILE_LOGGING") == "1":
        return False
    return "pytest" in sys.modules


def _remove_managed_handlers(logger: logging.Logger) -> None:
    """Удаляет только handlers, которыми управляет этот модуль."""
    for handler in list(logger.handlers):
        if getattr(handler, _MANAGED_HANDLER_ATTR, False):
            logger.removeHandler(handler)
            handler.close()


def _mark_managed(handler: logging.Handler) -> None:
    """Помечает handler как управляемый AntEx logging setup."""
    setattr(handler, _MANAGED_HANDLER_ATTR, True)


def _build_file_handler(
    *,
    log_dir: str,
    formatter: logging.Formatter,
    log_file_max_bytes: int,
    log_file_backup_count: int,
) -> RotatingFileHandler | None:
    """Создает ротируемый file handler для warning/error логов."""
    try:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path / "api.log",
            maxBytes=log_file_max_bytes,
            backupCount=log_file_backup_count,
            encoding="utf-8",
        )
    except OSError:
        logging.getLogger(__name__).warning(
            "File logging disabled: cannot create log directory %s",
            log_dir,
            exc_info=True,
        )
        return None

    handler.setLevel(logging.WARNING)
    handler.setFormatter(formatter)
    _mark_managed(handler)
    return handler


def _configure_external_loggers(level: int) -> None:
    """Синхронизирует уровни внешних логгеров."""
    for logger_name in ("uvicorn", "uvicorn.error", "aiogram"):
        logging.getLogger(logger_name).setLevel(level)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.setLevel(level)
    if not any(isinstance(filter_, HealthcheckAccessFilter) for filter_ in access_logger.filters):
        access_logger.addFilter(HealthcheckAccessFilter())
