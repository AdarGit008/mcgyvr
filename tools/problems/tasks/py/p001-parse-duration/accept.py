from solution import parse_duration

assert parse_duration("90s") == 90, "seconds only"
assert parse_duration("2h") == 7200, "single unit"
assert parse_duration("1h30m") == 5400, "two units"
assert parse_duration("1d2h3m4s") == 93784, "all four units"
assert parse_duration("0s") == 0, "zero is zero"
assert parse_duration("10m30s") == 630, "minutes and seconds"


def rejects(value):
    try:
        parse_duration(value)
    except ValueError:
        return True
    return False


assert rejects(""), "empty string is rejected"
assert rejects("30x"), "unknown unit is rejected"
assert rejects("1m1h"), "wrong order is rejected"
assert rejects("1h1h"), "repeated unit is rejected"
assert rejects("h"), "missing value is rejected"
assert rejects(42), "non-string is rejected"
print("ok")
