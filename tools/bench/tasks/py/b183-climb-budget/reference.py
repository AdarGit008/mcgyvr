import re


def climb_budget(tolls):
    """Cheapest way up a tolled scaffold whose tolls arrive as digit strings."""
    paid = []
    for index, written in enumerate(tolls):
        if not isinstance(written, str) or re.fullmatch(r"[0-9]+", written) is None:
            raise ValueError("rung %d is not written as digits" % index)
        if len(written) > 1 and written[0] == "0":
            raise ValueError("rung %d carries a leading zero" % index)
        paid.append(int(written))
    # Cheapest totals for standing two rungs back and one rung back.
    two_back = 0
    one_back = 0
    for toll in paid:
        here = toll + min(two_back, one_back)
        two_back = one_back
        one_back = here
    return min(two_back, one_back)
