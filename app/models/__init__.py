"""Экспорт всех моделей."""

from app.models.admin import Admin
from app.models.city import City
from app.models.config import Config
from app.models.order import Order
from app.models.rate import Rate
from app.models.user import User
from app.modules.broadcasts.models import Broadcast

__all__ = [
    "Admin",
    "Broadcast",
    "City",
    "Config",
    "Order",
    "Rate",
    "User",
]
