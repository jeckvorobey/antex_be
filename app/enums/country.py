"""Enums стран для городов."""

from __future__ import annotations

from enum import StrEnum


class Country(StrEnum):
    THAILAND = "thailand"
    VIETNAM = "vietnam"
    GEORGIA = "georgia"
    INTERNAL = "internal"

    @property
    def ru_name(self) -> str:
        return {
            Country.THAILAND: "Таиланд",
            Country.VIETNAM: "Вьетнам",
            Country.GEORGIA: "Грузия",
            Country.INTERNAL: "Внутренний обмен",
        }[self]

    @property
    def code(self) -> str:
        return {
            Country.THAILAND: "th",
            Country.VIETNAM: "vn",
            Country.GEORGIA: "ge",
            Country.INTERNAL: "internal",
        }[self]

    @property
    def flag(self) -> str:
        return {
            Country.THAILAND: "🇹🇭",
            Country.VIETNAM: "🇻🇳",
            Country.GEORGIA: "🇬🇪",
            Country.INTERNAL: "",
        }[self]
