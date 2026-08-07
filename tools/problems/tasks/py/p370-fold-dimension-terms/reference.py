import re

NAME = re.compile(r"[a-z]+")


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _read_units(raw):
    if not isinstance(raw, dict):
        raise ValueError("units must be a mapping")
    units = {}
    for name, exponent in raw.items():
        if not isinstance(name, str) or NAME.fullmatch(name) is None:
            raise ValueError("a unit name is a run of small letters")
        if not _whole(exponent) or exponent == 0:
            raise ValueError("an exponent is a whole number that is never zero")
        units[name] = exponent
    return units


def _read_term(raw):
    if not isinstance(raw, dict):
        raise ValueError("a term must be a mapping")
    if not isinstance(raw.get("op"), str):
        raise ValueError("a term needs an op")
    if not _whole(raw.get("count")):
        raise ValueError("a count must be a whole number")
    return raw["op"], raw["count"], _read_units(raw.get("units"))


def _tidy(units):
    return {name: exponent for name, exponent in units.items() if exponent != 0}


def fold_dimension_terms(terms: list) -> dict:
    if not isinstance(terms, list) or not terms:
        raise ValueError("there must be at least one term")
    op, count, units = _read_term(terms[0])
    if op != "=":
        raise ValueError("the first term must carry the op =")
    units = _tidy(units)

    for raw in terms[1:]:
        op, other, carried = _read_term(raw)
        if op == "*":
            count *= other
            next_units = dict(units)
            for name, exponent in carried.items():
                next_units[name] = next_units.get(name, 0) + exponent
            units = _tidy(next_units)
        elif op == "/":
            if other == 0:
                raise ValueError("a divisor's count may not be zero")
            if count % other != 0:
                raise ValueError("that division does not come out whole")
            count = count // other
            next_units = dict(units)
            for name, exponent in carried.items():
                next_units[name] = next_units.get(name, 0) - exponent
            units = _tidy(next_units)
        elif op in ("+", "-"):
            if units != carried:
                raise ValueError("unlike units cannot be added")
            count = count + other if op == "+" else count - other
        else:
            raise ValueError("a later op must be one of * / + -")

    return {"count": count, "units": units}
