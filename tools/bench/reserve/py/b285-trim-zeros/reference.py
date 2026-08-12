def trim_zeros(text: str) -> str:
    sign = "-" if text.startswith("-") else ""
    digits = text[1:] if sign else text
    if not digits.isdigit():
        return text
    return sign + (digits.lstrip("0") or "0")
