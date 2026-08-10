"""Expand one cron schedule field into the values it matches."""

import re


def _parse_part(text, what):
    if re.fullmatch(r"[0-9]+", text) is None:
        raise ValueError(what + " must be digits")
    return int(text)


def expand_cron_field(field: str, low: int, high: int) -> list:
    if not isinstance(field, str):
        raise ValueError("expand_cron_field expects a string field")
    if field == "":
        raise ValueError("empty field")
    matched = set()
    for item in field.split(","):
        if item == "":
            raise ValueError("empty item")
        pieces = item.split("/")
        if len(pieces) > 2:
            raise ValueError("more than one step")
        core = pieces[0]
        step = 1
        if len(pieces) == 2:
            step = _parse_part(pieces[1], "step")
            if step == 0:
                raise ValueError("step of zero")
        if core == "*":
            start, end = low, high
        elif "-" in core:
            ends = core.split("-")
            if len(ends) != 2:
                raise ValueError("malformed range")
            start = _parse_part(ends[0], "range low")
            end = _parse_part(ends[1], "range high")
            if start > end:
                raise ValueError("range low exceeds range high")
        else:
            if len(pieces) == 2:
                raise ValueError("step attached to a single number")
            start = _parse_part(core, "number")
            end = start
        if core != "*" and (start < low or end > high):
            raise ValueError("number outside the bounds")
        matched.update(range(start, end + 1, step))
    return sorted(matched)
