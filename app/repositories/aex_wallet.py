"""Re-export AexWalletRepository from canonical module.

This module exists for backward compatibility only.
The canonical definition lives in app.repositories.aex.
"""

from app.repositories.aex import AexWalletRepository

__all__ = ["AexWalletRepository"]
