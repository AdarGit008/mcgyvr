"""Sum a column of decimal amount strings exactly, by digit arithmetic."""

import re


def add_digits(a, b):
    carry = 0
    out = []
    for i in range(max(len(a), len(b))):
        da = int(a[len(a) - 1 - i]) if i < len(a) else 0
        db = int(b[len(b) - 1 - i]) if i < len(b) else 0
        carry, digit = divmod(da + db + carry, 10)
        out.append(str(digit))
    if carry:
        out.append(str(carry))
    return "".join(reversed(out))


def group_thousands(digits):
    grouped = []
    for i, ch in enumerate(digits):
        if i > 0 and (len(digits) - i) % 3 == 0:
            grouped.append("_")
        grouped.append(ch)
    return "".join(grouped)


def total_amounts(amounts: list) -> str:
    if not isinstance(amounts, list) or not amounts:
        raise ValueError("amounts must be a non-empty list")
    wholes = []
    fractions = []
    for amount in amounts:
        if not isinstance(amount, str):
            raise ValueError("each amount must be a string")
        if re.fullmatch(r"\d(?:_?\d)*(?:\.\d+)?", amount) is None:
            raise ValueError(f"malformed amount: {amount}")
        whole, _, fraction = amount.replace("_", "").partition(".")
        wholes.append(whole)
        fractions.append(fraction)
    scale = max(len(fraction) for fraction in fractions)
    total = "0"
    for whole, fraction in zip(wholes, fractions):
        total = add_digits(total, whole + fraction.ljust(scale, "0"))
    total = total.lstrip("0").rjust(scale + 1, "0")
    if scale == 0:
        return group_thousands(total)
    return f"{group_thousands(total[:-scale])}.{total[-scale:]}"
