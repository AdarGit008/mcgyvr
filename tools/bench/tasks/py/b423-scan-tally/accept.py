from solution import step_value, scan_tally

assert step_value("+") == 1, "a plus adds one"
assert step_value("-") == -1, "a minus takes one away"
assert step_value("x") == 0, "anything else adds nothing"
assert scan_tally(["+", "+"]) == [1, 2], "a total after each step"
assert scan_tally([]) == [], "no instructions at all"
assert scan_tally(["+", "-", "+"]) == [1, 0, 1], "the total moves both ways"
print("ok")
