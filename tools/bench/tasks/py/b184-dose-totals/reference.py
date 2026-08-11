import re


def dose_totals(log):
    """Exact per-reagent totals of a pour log, counted in thousandths."""
    thousandths = {}
    places = {}
    for reagent, amount in log:
        written = re.fullmatch(r"-?\d+(?:\.(\d{1,3}))?", amount)
        if written is None:
            raise ValueError("amount is not a decimal of at most three places: " + amount)
        digits = written.group(1) or ""
        sign = -1 if amount.startswith("-") else 1
        bare = amount.replace("-", "").replace(".", "")
        thousandths[reagent] = thousandths.get(reagent, 0) + sign * int(bare) * 10 ** (3 - len(digits))
        places[reagent] = max(places.get(reagent, 0), len(digits))
    totals = {}
    for reagent, kept in places.items():
        units = thousandths[reagent] // 10 ** (3 - kept)
        whole, rest = divmod(abs(units), 10 ** kept)
        body = str(whole) if kept == 0 else "%d.%0*d" % (whole, kept, rest)
        totals[reagent] = ("-" if units < 0 else "") + body
    return totals
