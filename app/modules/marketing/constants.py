"""Доменные константы marketing."""

from __future__ import annotations

import string

MARKETING_CODE_LENGTH = 10
MARKETING_CODE_ALPHABET = string.ascii_uppercase + string.digits
MARKETING_PROVIDERS = frozenset({"telegram_ads"})
MARKETING_CAMPAIGN_STATUSES = frozenset({"draft", "active", "paused", "archived"})
DEFAULT_MARKETING_PROVIDER = "telegram_ads"
