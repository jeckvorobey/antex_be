"""Экспорт репозиториев."""

from app.repositories.admin import AdminRepository
from app.repositories.allowance import AllowanceRepository
from app.repositories.bank import BankRepository
from app.repositories.bank_account import BankAccountRepository
from app.repositories.card import CardRepository
from app.repositories.config import ConfigRepository
from app.repositories.limitation import LimitationRepository
from app.repositories.order import OrderRepository
from app.repositories.rate import RateRepository
from app.repositories.review import ReviewRepository
from app.repositories.stat import StatRepository
from app.repositories.user import UserRepository

__all__ = [
    "AdminRepository",
    "AllowanceRepository",
    "BankAccountRepository",
    "BankRepository",
    "CardRepository",
    "ConfigRepository",
    "LimitationRepository",
    "OrderRepository",
    "RateRepository",
    "ReviewRepository",
    "StatRepository",
    "UserRepository",
]
