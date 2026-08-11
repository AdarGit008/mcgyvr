"""Canonical account handles from free-form display names."""

import re


def normalize_handle(raw):
    if not isinstance(raw, str):
        raise ValueError("normalize_handle expects a string")
    collapsed = re.sub(r"[ _-]+", "-", raw.strip().lower())
    if not collapsed:
        raise ValueError("handle is empty")
    if re.fullmatch(r"[a-z0-9-]+", collapsed) is None:
        raise ValueError("handle has an illegal character")
    if collapsed.startswith("-") or collapsed.endswith("-"):
        raise ValueError("handle may not begin or end with a hyphen")
    if not 3 <= len(collapsed) <= 20:
        raise ValueError("handle length out of range")
    return collapsed
