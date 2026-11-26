"""Database logic for Golden Pride."""
from __future__ import annotations
from .common import *

class Base(DeclarativeBase):
    pass

__all__ = [name for name in globals() if not name.startswith("__")]
