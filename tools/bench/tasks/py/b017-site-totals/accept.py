from solution import busiest_site, load_ledger, site_totals


def row(site, item, qty):
    return {"site": site, "item": item, "qty": qty}


assert site_totals([]) == [], "no rows means no totals"
assert site_totals([row("east", "pump", 5)]) == [
    ["east", 5]
], "a single row is its own total"
assert site_totals(
    [row("east", "pump", 3), row("west", "valve", 2), row("east", "hose", 4)]
) == [["east", 7], ["west", 2]], "a repeated site accumulates across its rows"
assert site_totals([row("west", "valve", 2), row("east", "pump", 3)]) == [
    ["east", 3],
    ["west", 2],
], "totals come back sorted by site name"
assert site_totals(
    [
        row("north", "pipe", 4),
        row("south", "clamp", 1),
        row("north", "pipe", 6),
        row("east", "pump", 2),
        row("south", "clamp", 3),
    ]
) == [["east", 2], ["north", 10], ["south", 4]], (
    "several sites with several repeats each"
)
assert site_totals(
    [row("mid", "bolt", 1), row("mid", "bolt", 2), row("mid", "bolt", 3)]
) == [["mid", 6]], "one site across three rows sums all three"


def rejects_totals(rows):
    try:
        site_totals(rows)
    except ValueError:
        return True
    return False


assert rejects_totals([row("east", "pump", 0)]), "zero qty"
assert rejects_totals([row("east", "pump", -3)]), "negative qty"
assert rejects_totals([row("east", "pump", 2.5)]), "fractional qty"
assert rejects_totals([row("east", "pump", True)]), "boolean qty"
assert (
    busiest_site([row("north", "pipe", 4), row("south", "clamp", 9), row("east", "pump", 2)])
    == "south"
), "the largest total wins"
assert busiest_site([row("west", "valve", 5), row("east", "pump", 5)]) == "east", (
    "a total tie goes to the alphabetically first site"
)
assert busiest_site([]) is None, "an empty ledger has no busiest site"
assert load_ledger(["east,pump,5", "west,valve,2"]) == [
    row("east", "pump", 5),
    row("west", "valve", 2),
], "load_ledger parses well-formed lines"


def rejects_ledger(lines):
    try:
        load_ledger(lines)
    except ValueError:
        return True
    return False


assert rejects_ledger(["east,pump"]), "a two-field line is rejected"
print("ok")
