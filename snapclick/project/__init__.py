"""Zapis/odczyt plików projektów .snapclick."""

from .storage import ProjectStorage, StorageError

__all__ = ["ProjectStorage", "StorageError"]
