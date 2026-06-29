from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler


def test_configure_logging_adds_console_and_warning_file_handler(tmp_path) -> None:
    from app.core.logging import configure_logging

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    try:
        for handler in original_handlers:
            root_logger.removeHandler(handler)

        configure_logging(
            log_dir=str(tmp_path),
            log_level="INFO",
            log_file_max_bytes=1024,
            log_file_backup_count=2,
        )

        file_handlers = [
            handler for handler in root_logger.handlers if isinstance(handler, RotatingFileHandler)
        ]
        assert len(file_handlers) == 1
        assert file_handlers[0].level == logging.WARNING
        assert file_handlers[0].maxBytes == 1024
        assert file_handlers[0].backupCount == 2

        app_logger = logging.getLogger("tests.logging_setup")
        app_logger.info("info should stay in console only")
        app_logger.warning("warning should be written to file")
        file_handlers[0].flush()

        log_file = tmp_path / "api.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "warning should be written to file" in content
        assert "info should stay in console only" not in content
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            root_logger.addHandler(handler)


def test_configure_logging_is_idempotent(tmp_path) -> None:
    from app.core.logging import configure_logging

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    try:
        for handler in original_handlers:
            root_logger.removeHandler(handler)

        configure_logging(log_dir=str(tmp_path), log_level="INFO")
        first_handlers = list(root_logger.handlers)
        configure_logging(log_dir=str(tmp_path), log_level="INFO")

        assert root_logger.handlers == first_handlers
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            root_logger.addHandler(handler)
