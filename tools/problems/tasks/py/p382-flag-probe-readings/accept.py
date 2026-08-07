from solution import flag_probe_readings

band = {"low": 0, "high": 100, "jump": 10, "stuck": 3}

assert flag_probe_readings([50, 55, 90, 90, 90, 90, 120, 95, 95], band) == [
    [],
    [],
    ["jump"],
    [],
    ["stuck"],
    ["stuck"],
    ["range"],
    [],
    [],
], "a mixed line flags the jump, the long run, and the out-of-band value"
assert flag_probe_readings([7], {"low": 0, "high": 10, "jump": 1, "stuck": 2}) == [
    []
], "a single plausible reading is unremarkable"
assert flag_probe_readings([7], {"low": 8, "high": 10, "jump": 1, "stuck": 2}) == [
    ["range"]
], "a single reading beneath low is out of band"
assert flag_probe_readings(
    [200, 200, 200], {"low": 0, "high": 100, "jump": 5, "stuck": 2}
) == [
    ["range"],
    ["range", "stuck"],
    ["range", "stuck"],
], "range and stuck may land on the same reading, in that order"
assert flag_probe_readings(
    [0, 40, 40], {"low": 0, "high": 100, "jump": 10, "stuck": 2}
) == [[], ["jump"], ["stuck"]], "a repeated jumped-to value stops jumping and starts sticking"
assert flag_probe_readings([5, 5, 6], {"low": 0, "high": 10, "jump": 0, "stuck": 5}) == [
    [],
    [],
    ["jump"],
], "a jump of zero makes any change a jump"
assert flag_probe_readings(
    [-5, -20, -21], {"low": -20, "high": 20, "jump": 100, "stuck": 9}
) == [[], [], ["range"]], "readings may be negative and low may be negative"
assert flag_probe_readings(
    [10, 300, 12], {"low": 0, "high": 100, "jump": 5, "stuck": 4}
) == [[], ["range"], []], "the out-of-band reading is skipped when the next reading looks back"
assert flag_probe_readings(
    [10, 300, 40], {"low": 0, "high": 100, "jump": 5, "stuck": 4}
) == [[], ["range"], ["jump"]], "the comparison still reaches back past the out-of-band reading"
assert flag_probe_readings(
    [4, 4, 4, 4, 9, 9, 4], {"low": 0, "high": 20, "jump": 9, "stuck": 3}
) == [[], [], ["stuck"], ["stuck"], [], [], []], "a changed value opens a run of length one"
assert flag_probe_readings([300, 300], {"low": 0, "high": 100, "jump": 5, "stuck": 3}) == [
    ["range"],
    ["range"],
], "an out-of-band run shorter than stuck carries range alone"


def rejects(readings, rules):
    try:
        flag_probe_readings(readings, rules)
    except ValueError:
        return True
    return False


assert rejects([], band), "an empty list is rejected"
assert rejects("50", band), "a non-list is rejected"
assert rejects([1, 2.5], band), "a fractional reading is rejected"
assert rejects([1], None), "a missing mapping is rejected"
assert rejects([1], [0, 100, 10, 3]), "a list of rules is rejected"
assert rejects([1], {"low": 0, "high": 100, "jump": 10}), "a missing stuck is rejected"
assert rejects([1], {"low": 100, "high": 0, "jump": 10, "stuck": 3}), "low above high is rejected"
assert rejects([1], {"low": 0, "high": 100, "jump": -1, "stuck": 3}), "a negative jump is rejected"
assert rejects([1], {"low": 0, "high": 100, "jump": 10, "stuck": 1}), "a stuck of one is rejected"
print("ok")
