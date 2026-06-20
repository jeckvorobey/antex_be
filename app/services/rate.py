"""Совместимость для форматирования курсов.

Основной SSOT логики обмена находится в app.services.exchange.
"""

from __future__ import annotations

from app.services.exchange import format_rate_value, get_client_rate, round_rate_value

__all__ = [
    "format_rate_value",
    "get_client_rate",
    "round_rate_value",
]
