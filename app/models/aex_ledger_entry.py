"""Re-export AexLedgerEntry from canonical module.

This module exists for backward compatibility only.
The canonical definition lives in app.models.aex.
"""

from app.models.aex import AexLedgerEntry

__all__ = ["AexLedgerEntry"]
