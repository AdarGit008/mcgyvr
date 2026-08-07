import re

ROW = re.compile(
    r"(?:([1-9][0-9]*) ([1-9][0-9]*)/([1-9][0-9]*)"
    r"|([1-9][0-9]*)/([1-9][0-9]*)"
    r"|([1-9][0-9]*)) (tsp|tbsp|cup|egg|g) ([A-Za-z]+(?: [A-Za-z]+)*)"
)

GRAIN = {
    "tsp": (1, 4),
    "tbsp": (1, 2),
    "cup": (1, 8),
    "egg": (1, 1),
    "g": (1, 1),
}


def _common_factor(a: int, b: int) -> int:
    while b != 0:
        a, b = b, a % b
    return a


def _check_part(top: int, bottom: int) -> None:
    if top >= bottom:
        raise ValueError("a part must be smaller than one: %d/%d" % (top, bottom))
    if _common_factor(top, bottom) != 1:
        raise ValueError("a part must already be reduced: %d/%d" % (top, bottom))


def rescale_recipe(lines: list, num: int, den: int) -> list:
    if not isinstance(lines, list):
        raise ValueError("the recipe must be a list of rows")
    for side in (num, den):
        if isinstance(side, bool) or not isinstance(side, int) or side < 1:
            raise ValueError("the ratio must be two whole numbers above zero")
    carried = set()
    out = []

    for row in lines:
        if not isinstance(row, str):
            raise ValueError("every row must be a string")
        hit = ROW.fullmatch(row)
        if hit is None:
            raise ValueError("the row breaks its shape: " + row)
        if hit.group(1) is not None:
            whole = int(hit.group(1))
            top = int(hit.group(2))
            bottom = int(hit.group(3))
            _check_part(top, bottom)
            over = whole * bottom + top
            under = bottom
        elif hit.group(4) is not None:
            top = int(hit.group(4))
            bottom = int(hit.group(5))
            _check_part(top, bottom)
            over = top
            under = bottom
        else:
            over = int(hit.group(6))
            under = 1
        unit = hit.group(7)
        ingredient = hit.group(8)
        if ingredient in carried:
            raise ValueError("two rows carry the same ingredient: " + ingredient)
        carried.add(ingredient)

        grain_top, grain_bottom = GRAIN[unit]
        top = over * num * grain_bottom
        bottom = under * den * grain_top
        grains = (2 * top + bottom) // (2 * bottom)
        if grains == 0:
            grains = 1
        value = grains * grain_top
        scale = grain_bottom
        shared = _common_factor(value, scale)
        value //= shared
        scale //= shared

        if scale == 1:
            amount = str(value)
        else:
            whole = value // scale
            rest = value % scale
            if whole == 0:
                amount = "%d/%d" % (rest, scale)
            else:
                amount = "%d %d/%d" % (whole, rest, scale)
        out.append(amount + " " + unit + " " + ingredient)
    return out
