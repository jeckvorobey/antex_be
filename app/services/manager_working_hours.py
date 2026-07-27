"""Единый UTC-расчёт режима работы менеджеров."""
# ruff: noqa: RUF001, RUF002

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal, Protocol

AvailabilityStatus = Literal["working", "offline", "unknown"]
_MSK_UTC_OFFSET_HOURS = 3
_WEEKDAY_LABELS = {
    "ru": {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"},
    "en": {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"},
}


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
    business_hours_text: str = "Ежедневно с 09:00 до 21:00 МСК"


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
            return ManagerAvailability(
                "unknown",
                False,
                days,
                start,
                end,
                None,
                None,
                None,
                self.format_business_hours(days, start, end),
            )

        current = (now or datetime.now(UTC)).astimezone(UTC)
        business_hours_text = self.format_business_hours(days, start, end)
        interval = self._find_containing_interval(current, days, start, end)
        if interval is not None:
            return ManagerAvailability(
                "working",
                True,
                days,
                start,
                end,
                interval[0],
                interval[1],
                None,
                business_hours_text,
            )

        next_start = self._find_next_start(current, days, start, end)
        return ManagerAvailability(
            "offline", True, days, start, end, None, None, next_start, business_hours_text
        )

    @staticmethod
    def format_business_hours(
        days: list[int],
        start: time,
        end: time,
        *,
        locale: str | None = None,
    ) -> str:
        """Формирует локализованную МСК-строку из сохранённого UTC-расписания."""
        language = "en" if (locale or "").split("-", 1)[0].lower() == "en" else "ru"
        utc_reference_date = datetime.min.date()
        start_msk_at = datetime.combine(utc_reference_date, start) + timedelta(
            hours=_MSK_UTC_OFFSET_HOURS
        )
        end_msk = (
            datetime.combine(utc_reference_date, end) + timedelta(hours=_MSK_UTC_OFFSET_HOURS)
        ).time()
        start_msk = start_msk_at.time()
        msk_days = sorted(
            ((day - 1 + (start_msk_at.date() - utc_reference_date).days) % 7) + 1 for day in days
        )
        if msk_days == list(range(1, 8)):
            days_text = "Daily" if language == "en" else "Ежедневно"
        elif msk_days == [1, 2, 3, 4, 5]:
            days_text = "Mon–Fri" if language == "en" else "Пн–Пт"
        else:
            days_text = ", ".join(_WEEKDAY_LABELS[language][day] for day in msk_days)
        if language == "en":
            return f"{days_text} from {start_msk:%H:%M} to {end_msk:%H:%M} MSK"
        return f"{days_text} с {start_msk:%H:%M} до {end_msk:%H:%M} МСК"

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
