"""Swap macro references for their values, following values in turn."""

import re

REFERENCE = re.compile(r"\$\(([a-z0-9]+)(?::([^()]*))?\)")


def _expand_into(text: str, macros: dict[str, str], active: tuple[str, ...]) -> str:
    def swap(found) -> str:
        name = found.group(1)
        if name in active:
            raise ValueError("macro cycle through " + name)
        if name in macros:
            return _expand_into(macros[name], macros, active + (name,))
        fallback = found.group(2)
        return "" if fallback is None else fallback

    return REFERENCE.sub(swap, text)


def expand_macro(text: str, macros: dict[str, str]) -> str:
    return _expand_into(text, macros, ())
