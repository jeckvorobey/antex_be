"""Экспорт всех моделей."""

from app.models.admin import Admin
from app.models.allowance import Allowance
from app.models.bank import Bank
from app.models.bank_account import BankAccount
from app.models.card import Card
from app.models.config import Config
from app.models.limitation import Limitation
from app.models.order import Order
from app.models.rate import Rate
from app.models.review import Review
from app.models.stat import Stat
from app.models.user import User

__all__ = [
    "Admin",
    "Allowance",
    "Bank",
    "BankAccount",
    "Card",
    "Config",
    "Limitation",
    "Order",
    "Rate",
    "Review",
    "Stat",
    "User",
]
