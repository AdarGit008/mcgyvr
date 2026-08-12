"""Fixed-point rendering and the report slots that lay the numbers out."""

import math


def format_fixed(value, decimals):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be a finite number")
    if not math.isfinite(value):
        raise ValueError("value must be a finite number")
    if isinstance(decimals, bool) or not isinstance(decimals, int):
        raise ValueError("decimals must be an integer from 0 to 6")
    if decimals < 0 or decimals > 6:
        raise ValueError("decimals must be an integer from 0 to 6")
    scale = 10 ** decimals
    scaled = int(abs(value) * scale + 0.5)
    whole = scaled // scale
    sign = "-" if value < 0 and scaled > 0 else ""
    if decimals == 0:
        return sign + str(whole)
    fraction = str(scaled % scale).rjust(decimals, "0")
    return f"{sign}{whole}.{fraction}"


def fill_report(template, values):
    if not isinstance(template, str):
        raise ValueError("template must be a string")
    out = []
    at = 0
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
    while at < len(template):
        ch = template[at]
        if ch != "[":
            out.append(ch)
            at += 1
            continue
        close = template.find("]", at + 1)
        if close < 0:
            raise ValueError("slot never closed")
        parts = template[at + 1:close].split(":")
        if len(parts) != 3:
            raise ValueError("a slot is name:width:decimals")
        name, width_text, decimals_text = parts
        if name == "" or any(c not in letters for c in name):
            raise ValueError(f"malformed slot name: {name}")
        if not width_text.isdigit() or int(width_text) < 1:
            raise ValueError("width must be a positive integer")
        if not decimals_text.isdigit():
            raise ValueError("decimals must be digits")
        if name not in values:
            raise ValueError(f"no value for slot: {name}")
        rendered = format_fixed(values[name], int(decimals_text))
        width = int(width_text)
        out.append(rendered if len(rendered) >= width else rendered.rjust(width, " "))
        at = close + 1
    return "".join(out)
