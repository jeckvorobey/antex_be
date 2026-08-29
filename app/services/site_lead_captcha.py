"""Self-hosted ALTCHA protection for public site leads."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from altcha import create_challenge, verify_solution
from fastapi import HTTPException, status

from app.core.config import settings

ALTCHA_TTL_SECONDS = 300
ALTCHA_CONTEXT = b"antex-site-lead-altcha-v2"


def create_site_lead_challenge() -> dict[str, object]:
    challenge = create_challenge(
        algorithm="PBKDF2/SHA-256",
        cost=5_000,
        expires_at=datetime.now(UTC) + timedelta(seconds=ALTCHA_TTL_SECONDS),
        hmac_secret=_altcha_secret(),
    )
    return challenge.to_dict()


async def verify_site_lead_captcha(payload: str) -> None:
    result = verify_solution(payload, _altcha_secret())
    if not result.verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Проверка защиты от спама не пройдена",
        )

    from app.core import redis as redis_module

    replay_hash = hashlib.sha256(payload.encode()).hexdigest()
    try:
        accepted = await redis_module.redis_client.set(
            f"site-lead:altcha:{replay_hash}",
            "1",
            ex=ALTCHA_TTL_SECONDS,
            nx=True,
        )
    except Exception as exc:
        if settings.app_env != "production":
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис заявок временно недоступен",
        ) from exc

    if not accepted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Проверка защиты от спама уже использована",
        )


def _altcha_secret() -> str:
    base_secret = settings.jwt_secret
    if not base_secret:
        if settings.app_env == "production":
            raise RuntimeError("JWT_SECRET is required for ALTCHA in production")
        base_secret = "antex-development-only-secret"
    return hmac.new(base_secret.encode(), ALTCHA_CONTEXT, hashlib.sha256).hexdigest()
