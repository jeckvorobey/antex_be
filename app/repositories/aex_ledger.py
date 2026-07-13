"""Re-export AexLedgerEntryRepository as AexLedgerRepository.

This module exists for backward compatibility only.
The canonical definition lives in app.repositories.aex.
"""

from app.repositories.aex import AexLedgerEntryRepository as AexLedgerRepository

__all__ = ["AexLedgerRepository"]
