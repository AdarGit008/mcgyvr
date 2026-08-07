from solution import best_rate_path


def rejects(quotes, amount, source, destination):
    try:
        best_rate_path(quotes, amount, source, destination)
    except ValueError:
        return True
    return False


assert best_rate_path([["USD", "EUR", 900000]], 1000, "USD", "EUR") == {
    "amount": 900,
    "path": ["USD", "EUR"],
}, "a single quote is the only run"

assert best_rate_path(
    [["USD", "EUR", 900000], ["EUR", "GBP", 900000], ["USD", "GBP", 800000]],
    1000,
    "USD",
    "GBP",
) == {"amount": 810, "path": ["USD", "EUR", "GBP"]}, "a detour can beat the direct quote"

assert best_rate_path(
    [["A", "B", 500000], ["B", "C", 2000000], ["A", "C", 1000000]], 7, "A", "C"
) == {"amount": 7, "path": ["A", "C"]}, "the discard at each hop separates the runs"

assert best_rate_path(
    [["A", "B", 1000000], ["B", "C", 1000000], ["A", "C", 1000000]], 500, "A", "C"
) == {"amount": 500, "path": ["A", "C"]}, "equal amounts break toward the shorter run"

assert best_rate_path(
    [
        ["A", "M", 1000000],
        ["M", "Z", 1000000],
        ["A", "N", 1000000],
        ["N", "Z", 1000000],
    ],
    100,
    "A",
    "Z",
) == {"amount": 100, "path": ["A", "M", "Z"]}, "equal lengths break on the codes"

assert best_rate_path(
    [["A", "B", 400000], ["B", "C", 5000000], ["A", "C", 900000]], 1, "A", "C"
) == {"amount": 0, "path": ["A", "C"]}, "a run may arrive at nothing and still win"

assert best_rate_path(
    [["JPY", "USD", 6000], ["USD", "CHF", 890000], ["JPY", "CHF", 5000]],
    1000000,
    "JPY",
    "CHF",
) == {
    "amount": 5340,
    "path": ["JPY", "USD", "CHF"],
}, "a three-code chain over a thin direct quote"

assert rejects([], 10, "A", "B"), "an empty quote list is rejected"
assert rejects([["A", "B"]], 10, "A", "B"), "a two-element quote is rejected"
assert rejects([["A", "", 100]], 10, "A", "B"), "an empty code is rejected"
assert rejects([["A", "A", 100]], 10, "A", "B"), "one code on both sides is rejected"
assert rejects([["A", "B", 0]], 10, "A", "B"), "a micro rate of zero is rejected"
assert rejects(
    [["A", "B", 100], ["A", "B", 200]], 10, "A", "B"
), "the same ordered pair quoted twice is rejected"
assert rejects([["A", "B", 100]], 0, "A", "B"), "an amount of zero is rejected"
assert rejects([["A", "B", 100]], 10, "A", "A"), "identical endpoints are rejected"
assert rejects([["A", "B", 100]], 10, "A", "Q"), "a code no quote names is rejected"
assert rejects(
    [["A", "B", 100]], 10, "B", "A"
), "a quote's direction cannot be run backwards"

print("ok")
