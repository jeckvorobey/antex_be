"""Re-export AexWallet from canonical module.

This module exists for backward compatibility only.
The canonical definition lives in app.models.aex.
"""

from app.models.aex import AexWallet

__all__ = ["AexWallet"]
