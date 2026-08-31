from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4


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
            disable_file_logging=False,
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

        network_logger = logging.getLogger("antex.network")
        network_handlers = [
            handler
            for handler in network_logger.handlers
            if isinstance(handler, RotatingFileHandler)
        ]
        assert len(network_handlers) == 1
        assert network_handlers[0].maxBytes == 1024
        assert network_handlers[0].backupCount == 2
        assert network_logger.propagate is False

        network_logger.info("ignored message", extra={"network_event": {"direction": "inbound"}})
        network_handlers[0].flush()
        record = json.loads((tmp_path / "network.log").read_text(encoding="utf-8"))
        assert record["direction"] == "inbound"
        assert "timestamp" in record
        assert "message" not in record
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

        configure_logging(log_dir=str(tmp_path), log_level="INFO", disable_file_logging=False)
        first_handlers = list(root_logger.handlers)
        first_network_handlers = list(logging.getLogger("antex.network").handlers)
        configure_logging(log_dir=str(tmp_path), log_level="INFO", disable_file_logging=False)

        assert root_logger.handlers == first_handlers
        assert logging.getLogger("antex.network").handlers == first_network_handlers
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            root_logger.addHandler(handler)


def test_configure_logging_skips_runtime_file_handler_under_pytest(tmp_path) -> None:
    from app.core.logging import configure_logging

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    try:
        for handler in original_handlers:
            root_logger.removeHandler(handler)

        configure_logging(log_dir=str(tmp_path), log_level="INFO")

        file_handlers = [
            handler for handler in root_logger.handlers if isinstance(handler, RotatingFileHandler)
        ]
        assert file_handlers == []
        assert logging.getLogger("antex.network").handlers == []
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            root_logger.addHandler(handler)


def test_network_log_rotates_with_configured_limit(tmp_path) -> None:
    from app.core.logging import configure_logging

    network_logger = logging.getLogger("antex.network")
    original_handlers = list(network_logger.handlers)
    original_propagate = network_logger.propagate
    try:
        configure_logging(
            log_dir=str(tmp_path),
            log_level="INFO",
            log_file_max_bytes=180,
            log_file_backup_count=2,
            disable_file_logging=False,
        )
        for index in range(10):
            network_logger.info(
                "ignored",
                extra={"network_event": {"direction": "inbound", "request_id": str(index)}},
            )
        for handler in network_logger.handlers:
            handler.flush()

        assert (tmp_path / "network.log").exists()
        assert (tmp_path / "network.log.1").exists()
    finally:
        for handler in list(network_logger.handlers):
            network_logger.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            network_logger.addHandler(handler)
        network_logger.propagate = original_propagate


def test_pytest_warning_does_not_write_to_developer_runtime_api_log(tmp_path) -> None:
    from app.core.logging import configure_logging

    del tmp_path
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    runtime_log = Path("logs/api.log")
    marker = f"pytest-runtime-log-isolation-{uuid4()}"
    try:
        for handler in original_handlers:
            root_logger.removeHandler(handler)

        configure_logging(log_dir="logs", log_level="INFO")
        logging.getLogger("tests.logging_setup").warning(marker)
        for handler in root_logger.handlers:
            handler.flush()

        if runtime_log.exists():
            assert marker not in runtime_log.read_text(encoding="utf-8")
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            root_logger.addHandler(handler)
