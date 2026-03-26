#!/usr/bin/env python3
"""
Точка входа для запуска AntEx backend.

Использование:
    uv run python run.py                    # Запуск с автоперезагрузкой
    uv run python run.py --no-reload        # Запуск без автоперезагрузки
    uv run python run.py --host 0.0.0.0     # Запуск на всех интерфейсах
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import uvicorn  # noqa: F401
    from dotenv import load_dotenv
except ImportError:
    print("uvicorn или python-dotenv не установлены!")
    print("\nУстановите зависимости:")
    print("   cd back")
    print("   uv sync")
    print("   uv run python run.py")
    sys.exit(1)


def _build_uvicorn_command(config: dict[str, Any]) -> list[str]:
    cmd = [
        sys.executable, "-m", "uvicorn",
        config["app"],
        "--host", config["host"],
        "--port", str(config["port"]),
        "--log-level", config["log_level"],
    ]
    if config["reload"]:
        cmd.append("--reload")
    if config["access_log"]:
        cmd.append("--access-log")
    else:
        cmd.append("--no-access-log")
    return cmd


def _start_server(cmd: list[str], workdir: Path) -> subprocess.Popen[str]:
    popen_kwargs: dict[str, Any] = {"cwd": str(workdir), "text": True}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **popen_kwargs)


def _terminate_process_tree(proc: subprocess.Popen[str], timeout: float = 10.0) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception:
            proc.terminate()
    else:
        try:
            os.killpg(proc.pid, signal.SIGINT)
        except ProcessLookupError:
            return
    try:
        proc.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        proc.terminate()
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def main() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path)

    config = {
        "app": "app.main:app",
        "host": os.getenv("APP_HOST", "127.0.0.1"),
        "port": int(os.getenv("APP_PORT", "8000")),
        "reload": True,
        "log_level": "info",
        "access_log": True,
    }

    if "--no-reload" in sys.argv:
        config["reload"] = False
    if "--host" in sys.argv:
        try:
            config["host"] = sys.argv[sys.argv.index("--host") + 1]
        except (IndexError, ValueError):
            sys.exit(1)
    if "--port" in sys.argv:
        try:
            config["port"] = int(sys.argv[sys.argv.index("--port") + 1])
        except (IndexError, ValueError):
            sys.exit(1)

    print(f"Запуск AntEx Backend на http://{config['host']}:{config['port']}")
    print(f"Автоперезагрузка: {'вкл' if config['reload'] else 'выкл'}")

    cmd = _build_uvicorn_command(config)
    workdir = Path(__file__).resolve().parent
    proc = _start_server(cmd, workdir)
    shutdown_requested = False

    def _handle_signal(_signum: int, _frame: object | None) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        _terminate_process_tree(proc)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        exit_code = proc.wait()
    except KeyboardInterrupt:
        _handle_signal(signal.SIGINT, None)
        exit_code = proc.wait()

    graceful_codes = {0, -signal.SIGTERM, -signal.SIGINT, -signal.SIGKILL, 130, 143}
    if exit_code == 0 or (shutdown_requested and exit_code in graceful_codes):
        return
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
