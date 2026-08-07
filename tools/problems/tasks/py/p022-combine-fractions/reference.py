import math
import re


def combine_fractions(parts: list[str]) -> str:
    if not isinstance(parts, list) or not parts:
        raise ValueError("combine_fractions expects a non-empty list")
    num = 0
    den = 1
    for part in parts:
        if not isinstance(part, str) or re.fullmatch(r"-?\d+/\d+", part) is None:
            raise ValueError(f"malformed fraction: {part!r}")
        a, b = part.split("/")
        n = int(a)
        d = int(b)
        if d == 0:
            raise ValueError(f"zero denominator: {part}")
        num = num * d + n * den
        den = den * d
        g = math.gcd(num, den)
        if g > 1:
            num //= g
            den //= g
    if num == 0:
        return "0/1"
    return f"{num}/{den}"
