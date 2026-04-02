"""Экспорт репозиториев."""

from app.repositories.admin import AdminRepository
from app.repositories.city import CityRepository
from app.repositories.config import ConfigRepository
from app.repositories.order import OrderRepository
from app.repositories.rate import RateRepository
from app.repositories.user import UserRepository

__all__ = [
    "AdminRepository",
    "CityRepository",
    "ConfigRepository",
    "OrderRepository",
    "RateRepository",
    "UserRepository",
]
