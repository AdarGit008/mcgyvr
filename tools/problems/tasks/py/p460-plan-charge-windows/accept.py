from solution import plan_charge_windows


def band(label, opens, shuts, price, rate, blocked=False):
    return {"label": label, "opens": opens, "shuts": shuts, "price": price, "rate": rate, "blocked": blocked}


night = [band("peak", 0, 4, 30, 5), band("night", 4, 10, 7, 4), band("day", 10, 14, 18, 6)]

assert plan_charge_windows(night, 20) == {"plan": [["night", 20]], "cost": 140, "short": 0}, (
    "a target the cheapest window swallows whole leaves the others alone"
)
assert plan_charge_windows(night, 30) == {"plan": [["night", 24], ["day", 6]], "cost": 276, "short": 0}, (
    "the overflow goes to the next cheapest window"
)
assert plan_charge_windows(night, 100) == {
    "plan": [["peak", 20], ["night", 24], ["day", 24]],
    "cost": 1200,
    "short": 32,
}, "a target past every window's room leaves a shortfall"
assert plan_charge_windows(night, 0) == {"plan": [], "cost": 0, "short": 0}, "asking for nothing draws nothing"
assert plan_charge_windows([band("peak", 0, 4, 30, 5), band("night", 4, 10, 7, 4, True)], 10) == {
    "plan": [["peak", 10]],
    "cost": 300,
    "short": 0,
}, "a barred window is passed over however cheap it is"
assert plan_charge_windows([band("late", 8, 10, 5, 3), band("early", 0, 2, 5, 3)], 8) == {
    "plan": [["early", 6], ["late", 2]],
    "cost": 40,
    "short": 0,
}, "windows at one price are drawn from in clock order"
assert plan_charge_windows([], 5) == {"plan": [], "cost": 0, "short": 5}, (
    "no windows at all leaves the whole target short"
)
assert plan_charge_windows([band("a", 0, 2, 4, 3)], 6) == {"plan": [["a", 6]], "cost": 24, "short": 0}, (
    "a target that fills one window exactly"
)
assert plan_charge_windows([band("a", 0, 2, 0, 3), band("b", 2, 4, 9, 3)], 8) == {
    "plan": [["a", 6], ["b", 2]],
    "cost": 18,
    "short": 0,
}, "a window priced at nothing is drawn on first and adds nothing"
assert plan_charge_windows([band("a", 0, 5, 2, 1), band("b", 5, 10, 1, 1)], 7) == {
    "plan": [["a", 2], ["b", 5]],
    "cost": 9,
    "short": 0,
}, "the plan is reported by the clock even when the cheap window comes last"


def rejects(windows, target):
    try:
        plan_charge_windows(windows, target)
    except ValueError:
        return True
    return False


assert rejects("no", 5), "windows that are not a list are refused"
assert rejects([], -1), "a negative target is refused"
assert rejects([], 1.5), "a fractional target is refused"
assert rejects([[1, 2]], 5), "a window that is not a record is refused"
assert rejects([band("", 0, 1, 1, 1)], 5), "an empty label is refused"
assert rejects([band("a", 0, 1, 1, 1), band("a", 2, 3, 1, 1)], 5), "one label twice is refused"
assert rejects([band("a", -1, 1, 1, 1)], 5), "an opening before nought is refused"
assert rejects([band("a", 3, 3, 1, 1)], 5), "a window that shuts as it opens is refused"
assert rejects([band("a", 3, 2, 1, 1)], 5), "a window that shuts before it opens is refused"
assert rejects([band("a", 0, 1, -1, 1)], 5), "a negative price is refused"
assert rejects([band("a", 0, 1, 1, 0)], 5), "a rate of nought is refused"
assert rejects([band("a", 0, 1, 1, 1.5)], 5), "a fractional rate is refused"
assert rejects([band("a", 0, 1, 1, 1, "no")], 5), "a bar that is not a boolean is refused"
assert rejects([band("a", 0, 5, 1, 1), band("b", 4, 9, 1, 1)], 5), "two windows sharing time are refused"
print("ok")
