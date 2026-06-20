from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services.order_numbers import OrderNumberService


@pytest.mark.asyncio
async def test_public_number_is_monotonic_within_year(db_session) -> None:
    service = OrderNumberService(db_session)

    may_number = await service.next_public_number(
        created_at=datetime(2026, 5, 22, 10, 0, tzinfo=UTC)
    )
    december_number = await service.next_public_number(
        created_at=datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
    )

    assert may_number == "2026050001"
    assert december_number == "2026120002"


@pytest.mark.asyncio
async def test_public_number_resets_when_year_changes(db_session) -> None:
    service = OrderNumberService(db_session)

    await service.next_public_number(created_at=datetime(2026, 12, 31, 20, 0, tzinfo=UTC))
    january_number = await service.next_public_number(
        created_at=datetime(2027, 1, 1, 1, 0, tzinfo=UTC)
    )

    assert january_number == "2027010001"
