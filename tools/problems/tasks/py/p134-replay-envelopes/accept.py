from solution import replay_envelopes


def env(name, monthly, cap):
    return {"name": name, "monthly": monthly, "cap": cap}


assert replay_envelopes([env("a", 100, 50)], [[]]) == {
    "balances": [["a", 50]],
    "forfeited": 50,
}, "an over-cap close forfeits the excess"
assert replay_envelopes([env("a", 40, 20)], [[["a", 30]]]) == {
    "balances": [["a", 10]],
    "forfeited": 0,
}, "deposit, then outlays, then cap - never cap before spending"
assert replay_envelopes([env("a", 10, 100)], [[["a", 25]], []]) == {
    "balances": [["a", -5]],
    "forfeited": 0,
}, "debt carries in full and the next deposit lands on top of it"
assert replay_envelopes([env("a", 30, 100)], [[["a", 10]], []]) == {
    "balances": [["a", 50]],
    "forfeited": 0,
}, "an under-cap balance rolls into the next month untouched"
assert replay_envelopes([env("b", 5, 99), env("a", 7, 99)], [[]]) == {
    "balances": [["b", 5], ["a", 7]],
    "forfeited": 0,
}, "balances keep declaration order, not name order"
assert replay_envelopes([env("a", 60, 50)], [[], []]) == {
    "balances": [["a", 50]],
    "forfeited": 70,
}, "forfeits accumulate month after month"
assert replay_envelopes([env("a", 9, 5)], []) == {
    "balances": [["a", 0]],
    "forfeited": 0,
}, "no months means untouched zero balances"
assert replay_envelopes(
    [env("food", 50, 40), env("fun", 20, 100)], [[["food", 30], ["fun", 5]]]
) == {
    "balances": [["food", 20], ["fun", 15]],
    "forfeited": 0,
}, "outlays hit only the envelope they name"


def rejects(envelopes, months):
    try:
        replay_envelopes(envelopes, months)
    except ValueError:
        return True
    return False


assert rejects(
    [env("a", 5, 5)], [[["ghost", 1]]]
), "an outlay on an unknown envelope is rejected"
assert rejects(
    [env("a", 5, 5), env("a", 1, 1)], []
), "a duplicate envelope name is rejected"
assert rejects([env("a", -5, 5)], []), "a negative monthly is rejected"
assert rejects([env("a", 5, 1.5)], []), "a fractional cap is rejected"
assert rejects([env("a", 5, 5)], [[["a", 0]]]), "a zero outlay is rejected"
assert rejects([env("", 5, 5)], []), "an empty envelope name is rejected"
print("ok")
