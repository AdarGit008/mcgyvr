"""Concrete language adapters.

Each module here implements :class:`mcgyvr.gate.adapter.LanguageAdapter` for one
language. The Python adapter is the reference; the JS/TS adapter (#36) proves
the interface is real rather than Python-shaped.
"""

from __future__ import annotations

from mcgyvr.gate.adapters.javascript import JavaScriptAdapter
from mcgyvr.gate.adapters.python import PythonAdapter

__all__ = ["JavaScriptAdapter", "PythonAdapter"]
