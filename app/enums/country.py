"""Enums стран для городов."""

from __future__ import annotations

from enum import StrEnum


class Country(StrEnum):
    THAILAND = "thailand"
    VIETNAM = "vietnam"

    @property
    def ru_name(self) -> str:
        return {
            Country.THAILAND: "Таиланд",
            Country.VIETNAM: "Вьетнам",
        }[self]

    @property
    def code(self) -> str:
        return {
            Country.THAILAND: "th",
            Country.VIETNAM: "vn",
        }[self]

    @property
    def flag(self) -> str:
        return {
            Country.THAILAND: "🇹🇭",
            Country.VIETNAM: "🇻🇳",
        }[self]
