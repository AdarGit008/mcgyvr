from math import gcd


def lowest_terms(top, bottom):
    divisor = gcd(top, bottom)
    return top // divisor, bottom // divisor


def combine_measures(pours, factor):
    if not isinstance(pours, list):
        raise ValueError("pours must be a list")
    if not isinstance(factor, list) or len(factor) != 2:
        raise ValueError("the factor is [numerator, denominator]")
    for part in factor:
        if isinstance(part, bool) or not isinstance(part, int) or part <= 0:
            raise ValueError("factor parts must be positive integers")
    totals = {}
    for entry in pours:
        if not isinstance(entry, list) or len(entry) != 3:
            raise ValueError("an entry is [name, numerator, denominator]")
        name, num, den = entry
        if not isinstance(name, str) or not name:
            raise ValueError("names must be non-empty strings")
        for part in (num, den):
            if isinstance(part, bool) or not isinstance(part, int):
                raise ValueError("quantities must be integer fractions")
        if den <= 0:
            raise ValueError("quantity denominators must be positive")
        held_num, held_den = totals.get(name, (0, 1))
        top = held_num * den + num * held_den
        totals[name] = lowest_terms(top, held_den * den)
    mixed = []
    for name in sorted(totals):
        num, den = totals[name]
        top, bottom = lowest_terms(num * factor[0], den * factor[1])
        mixed.append([name, top, bottom])
    return mixed
