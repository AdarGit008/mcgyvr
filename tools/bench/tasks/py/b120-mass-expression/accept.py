from solution import mass_expression

assert mass_expression("2kg + 300g", "g") == 2300, "kilograms and grams add up"
assert mass_expression("0g", "g") == 0, "a zero tally counts zero"
assert mass_expression("1t - 200kg", "kg") == 800, "a draw comes off the tonne"
assert mass_expression("1g - 1g + 5kg", "kg") == 5, "the tally may touch zero and refill"
assert mass_expression("3kg + 500g + 500g", "kg") == 4, "a whole total converts upward"


def rejects(text, unit):
    try:
        mass_expression(text, unit)
    except Exception:
        return True
    return False


assert rejects(42, "g"), "a non-string tally is rejected"
assert rejects("", "g"), "an empty tally is rejected"
assert rejects("1g +", "g"), "a tally ending on an operator is rejected"
assert rejects("2kg+300g", "g"), "missing spaces are rejected"
assert rejects("02g", "g"), "a leading zero is rejected"
assert rejects("2lb", "g"), "an unknown unit is rejected"
assert rejects("1g * 2g", "g"), "an unknown operator is rejected"
assert rejects("3g - 5g + 4g", "g"), "dipping below zero is rejected"
assert rejects("500g", "lb"), "an unknown goal unit is rejected"
assert rejects("1500g", "kg"), "a fractional total is rejected"
print("ok")
