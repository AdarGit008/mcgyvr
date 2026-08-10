"""Fixed-point money helpers: parse, format, and allocate integer cents."""

import re


def parse_amount(text: str) -> int:
    if not isinstance(text, str):
        raise ValueError("amount must be a string")
    match = re.fullmatch(r"(\d+)(?:\.(\d{2}))?", text)
    if match is None:
        raise ValueError(f"malformed amount: {text}")
    whole = int(match.group(1))
    cents = 0 if match.group(2) is None else int(match.group(2))
    return whole * 100 + cents


def format_amount(cents: int) -> str:
    if isinstance(cents, bool) or not isinstance(cents, int) or cents < 0:
        raise ValueError("cents must be a non-negative integer")
    return f"{cents // 100}.{cents % 100:02d}"


def allocate_cents(total_cents: int, weights: list) -> list:
    if isinstance(total_cents, bool) or not isinstance(total_cents, int):
        raise ValueError("total must be a non-negative integer")
    if total_cents < 0:
        raise ValueError("total must be a non-negative integer")
    if not weights:
        raise ValueError("weights must not be empty")
    for weight in weights:
        if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
            raise ValueError("weights must be non-negative integers")
    sum_w = sum(weights)
    if sum_w == 0:
        raise ValueError("weights must not sum to zero")
    shares = []
    remainders = []
    for weight in weights:
        exact = total_cents * weight
        shares.append(exact // sum_w)
        remainders.append(exact % sum_w)
    leftover = total_cents - sum(shares)
    order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
    for index in order:
        if leftover == 0:
            break
        shares[index] += 1
        leftover -= 1
    return shares
