from __future__ import annotations

from run import _build_uvicorn_command


def test_uvicorn_command_trusts_only_configured_proxy_networks() -> None:
    command = _build_uvicorn_command(
        {
            "app": "app.main:app",
            "host": "0.0.0.0",
            "port": 8000,
            "log_level": "info",
            "reload": False,
            "access_log": False,
            "forwarded_allow_ips": "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,::1,fc00::/7",
        }
    )

    option_index = command.index("--forwarded-allow-ips")
    assert command[option_index + 1] == (
        "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,::1,fc00::/7"
    )
    assert "*" not in command
    assert "--no-access-log" in command
    assert "--access-log" not in command
