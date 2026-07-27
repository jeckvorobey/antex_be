from __future__ import annotations

from datetime import UTC, datetime, time
from types import SimpleNamespace

from app.services.manager_working_hours import ManagerWorkingHoursService


def _config(**overrides):
    values = {
        "manager_schedule_enabled": True,
        "manager_working_days_utc": [1, 2, 3, 4, 5, 6, 7],
        "manager_start_time_utc": time(6),
        "manager_end_time_utc": time(18),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_service_returns_working_at_start_and_offline_at_end() -> None:
    service = ManagerWorkingHoursService()

    started = service.get_availability(_config(), now=datetime(2026, 7, 27, 6, tzinfo=UTC))
    ended = service.get_availability(_config(), now=datetime(2026, 7, 27, 18, tzinfo=UTC))

    assert started.status == "working"
    assert started.current_end_at == datetime(2026, 7, 27, 18, tzinfo=UTC)
    assert ended.status == "offline"
    assert ended.next_start_at == datetime(2026, 7, 28, 6, tzinfo=UTC)


def test_service_finds_next_enabled_day_and_overnight_interval() -> None:
    service = ManagerWorkingHoursService()
    weekdays = _config(manager_working_days_utc=[1, 3, 5])
    overnight = _config(
        manager_working_days_utc=[1],
        manager_start_time_utc=time(21),
        manager_end_time_utc=time(3),
    )

    next_day = service.get_availability(weekdays, now=datetime(2026, 7, 28, 12, tzinfo=UTC))
    night = service.get_availability(overnight, now=datetime(2026, 7, 28, 2, tzinfo=UTC))

    assert next_day.status == "offline"
    assert next_day.next_start_at == datetime(2026, 7, 29, 6, tzinfo=UTC)
    assert night.status == "working"
    assert night.current_start_at == datetime(2026, 7, 27, 21, tzinfo=UTC)
    assert night.current_end_at == datetime(2026, 7, 28, 3, tzinfo=UTC)


def test_service_formats_business_hours_from_actual_utc_schedule_in_msk() -> None:
    service = ManagerWorkingHoursService()
    custom_schedule = _config(
        manager_working_days_utc=[1, 2, 3, 4, 5],
        manager_start_time_utc=time(7),
        manager_end_time_utc=time(19),
    )

    availability = service.get_availability(
        custom_schedule,
        now=datetime(2026, 7, 27, 8, tzinfo=UTC),
    )

    assert availability.business_hours_text == "Пн–Пт с 10:00 до 22:00 МСК"  # noqa: RUF001


def test_service_shifts_weekday_labels_with_schedule_start_to_msk() -> None:
    service = ManagerWorkingHoursService()
    overnight_schedule = _config(
        manager_working_days_utc=[1],
        manager_start_time_utc=time(21),
        manager_end_time_utc=time(3),
    )

    availability = service.get_availability(
        overnight_schedule,
        now=datetime(2026, 7, 27, 22, tzinfo=UTC),
    )

    assert availability.business_hours_text == "Вт с 00:00 до 06:00 МСК"  # noqa: RUF001


def test_service_returns_unknown_for_disabled_or_invalid_schedule() -> None:
    service = ManagerWorkingHoursService()

    assert service.get_availability(_config(manager_schedule_enabled=False)).status == "unknown"
    assert service.get_availability(None).status == "unknown"
