"""Единый UTC-расчёт режима работы менеджеров."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal, Protocol

AvailabilityStatus = Literal["working", "offline", "unknown"]


class ManagerScheduleConfig(Protocol):
    """Минимальный контракт singleton-настройки для расчёта рабочего интервала."""

    manager_schedule_enabled: bool
    manager_working_days_utc: list[int]
    manager_start_time_utc: time
    manager_end_time_utc: time


@dataclass(frozen=True, slots=True)
class ManagerAvailability:
    """Снимок доступности менеджеров, безопасный для передачи в пользовательские DTO."""

    status: AvailabilityStatus
    schedule_enabled: bool
    working_days_utc: list[int]
    start_time_utc: time
    end_time_utc: time
    current_start_at: datetime | None
    current_end_at: datetime | None
    next_start_at: datetime | None
    business_hours_text: str = "Ежедневно с 09:00 до 21:00 МСК"  # noqa: RUF001


class ManagerWorkingHoursService:
    """Строит availability по singleton-конфигурации без зависимости от timezone процесса."""

    def get_availability(
        self,
        config: ManagerScheduleConfig | None,
        *,
        now: datetime | None = None,
    ) -> ManagerAvailability:
        """Возвращает текущий либо ближайший UTC-интервал; ошибка конфигурации даёт unknown."""
        try:
            if config is None:
                raise ValueError("Missing config")
            enabled = bool(config.manager_schedule_enabled)
            days = sorted({int(day) for day in config.manager_working_days_utc})
            start = config.manager_start_time_utc
            end = config.manager_end_time_utc
            if (
                not days
                or any(day < 1 or day > 7 for day in days)
                or not isinstance(start, time)
                or not isinstance(end, time)
            ):
                raise ValueError("Invalid manager schedule")
        except (AttributeError, TypeError, ValueError):
            return ManagerAvailability("unknown", False, [], time(0), time(0), None, None, None)

        if not enabled:
            return ManagerAvailability("unknown", False, days, start, end, None, None, None)

        current = (now or datetime.now(UTC)).astimezone(UTC)
        interval = self._find_containing_interval(current, days, start, end)
        if interval is not None:
            return ManagerAvailability(
                "working", True, days, start, end, interval[0], interval[1], None
            )

        next_start = self._find_next_start(current, days, start, end)
        return ManagerAvailability("offline", True, days, start, end, None, None, next_start)

    @staticmethod
    def _interval_for_date(day: datetime.date, start: time, end: time) -> tuple[datetime, datetime]:
        """Строит UTC-интервал, поддерживая завершение смены в следующий календарный день."""
        start_at = datetime.combine(day, start, tzinfo=UTC)
        end_at = datetime.combine(day, end, tzinfo=UTC)
        if end <= start:
            end_at += timedelta(days=1)
        return start_at, end_at

    def _find_containing_interval(
        self,
        now: datetime,
        days: list[int],
        start: time,
        end: time,
    ) -> tuple[datetime, datetime] | None:
        for offset in (0, -1):
            date = (now + timedelta(days=offset)).date()
            if date.isoweekday() not in days:
                continue
            interval = self._interval_for_date(date, start, end)
            if interval[0] <= now < interval[1]:
                return interval
        return None

    def _find_next_start(self, now: datetime, days: list[int], start: time, end: time) -> datetime:
        for offset in range(0, 8):
            date = (now + timedelta(days=offset)).date()
            if date.isoweekday() not in days:
                continue
            start_at, _ = self._interval_for_date(date, start, end)
            if start_at > now:
                return start_at
        raise RuntimeError("Manager schedule contains no future interval")
