def divide_fixed(numerator: int, denominator: int, places: int) -> str:
    for value in (numerator, denominator, places):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("divide_fixed expects integer arguments")
    if denominator == 0:
        raise ValueError("division by zero")
    if places < 0 or places > 6:
        raise ValueError("places must be within 0..6")
    negative = (numerator < 0) != (denominator < 0)
    n = abs(numerator)
    d = abs(denominator)
    scaled = n * 10**places
    q, r = divmod(scaled, d)
    if 2 * r > d or (2 * r == d and q % 2 == 1):
        q += 1
    digits = str(q).rjust(places + 1, "0")
    whole = digits[: len(digits) - places]
    frac = "." + digits[len(digits) - places :] if places > 0 else ""
    sign = "-" if negative and q != 0 else ""
    return sign + whole + frac
