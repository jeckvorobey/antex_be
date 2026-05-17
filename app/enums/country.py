"""Enums стран для городов."""

from __future__ import annotations

from enum import StrEnum


class Country(StrEnum):
    THAILAND = "thailand"
    VIETNAM = "vietnam"
    GEORGIA = "georgia"

    @property
    def ru_name(self) -> str:
        return {
            Country.THAILAND: "Тайланд",
            Country.VIETNAM: "Вьетнам",
            Country.GEORGIA: "Грузия",
        }[self]

    @property
    def code(self) -> str:
        return {
            Country.THAILAND: "th",
            Country.VIETNAM: "vn",
            Country.GEORGIA: "ge",
        }[self]

    @property
    def flag(self) -> str:
        return {
            Country.THAILAND: "🇹🇭",
            Country.VIETNAM: "🇻🇳",
            Country.GEORGIA: "🇬🇪",
        }[self]
