"""Tape-measure spans: parse to inches, format canonically, and add."""

import re

INCHES = {"yd": 36, "ft": 12, "in": 1}
ORDER = ("yd", "ft", "in")


def parse_span(text: str) -> int:
    if not isinstance(text, str):
        raise ValueError("a span must be a string")
    if text == "":
        raise ValueError("a span must not be empty")
    total = 0
    rank = -1
    for part in text.split(" "):
        match = re.fullmatch(r"(0|[1-9]\d*)([a-z]+)", part)
        if match is None:
            raise ValueError(f"malformed span part: {part}")
        unit = match.group(2)
        if unit not in INCHES:
            raise ValueError(f"unknown unit: {unit}")
        at = ORDER.index(unit)
        if at <= rank:
            raise ValueError(f"units out of order or repeated: {part}")
        rank = at
        total += int(match.group(1)) * INCHES[unit]
    return total


def format_span(inches: int) -> str:
    if isinstance(inches, bool) or not isinstance(inches, int) or inches < 0:
        raise ValueError("inches must be a non-negative integer")
    if inches == 0:
        return "0in"
    parts = []
    yards, rest = divmod(inches, 36)
    feet, rest = divmod(rest, 12)
    if yards:
        parts.append(f"{yards}yd")
    if feet:
        parts.append(f"{feet}ft")
    if rest:
        parts.append(f"{rest}in")
    return " ".join(parts)


def add_spans(first: str, second: str) -> str:
    total = parse_span(first) + parse_span(second)
    return format_span(total)
