"""Доменные константы marketing."""

from __future__ import annotations

import string

MARKETING_CODE_LENGTH = 10
MARKETING_CODE_ALPHABET = string.ascii_uppercase + string.digits
MARKETING_START_PARAM_PREFIX = "mkt_"
MARKETING_CODE_PREVIEW_TOKEN_TYPE = "marketing_code_preview"
MARKETING_CODE_PREVIEW_TTL_SECONDS = 15 * 60
MARKETING_CAMPAIGN_STATUSES = frozenset({"draft", "active", "paused", "archived"})
DEFAULT_MARKETING_PLATFORM_SLUG = "telegram_ads"
DEFAULT_MARKETING_PLATFORM_NAME = "Telegram Ads"
DEFAULT_MARKETING_CURRENCY_CODE = "USDT"
