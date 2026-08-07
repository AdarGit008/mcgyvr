from solution import calibrate_raw_count

assert calibrate_raw_count([[0, 0], [100, 500]], 50) == "250", "the midpoint of one segment"
assert calibrate_raw_count([[0, 0], [100, 500]], 25) == "125", "a quarter of the way along"
assert calibrate_raw_count([[0, 0], [100, 500]], 0) == "0", "the opening breakpoint itself"
assert calibrate_raw_count([[0, 0], [100, 500]], 100) == "500", "the closing breakpoint itself"
assert calibrate_raw_count([[0, 0], [3, 1]], 1) == "1/3", "a third stays a fraction"
assert calibrate_raw_count([[0, 0], [3, 1]], 2) == "2/3", "two thirds stays a fraction"
assert calibrate_raw_count([[0, 0], [3, 1]], -5) == "0", "a count under the table clamps low"
assert calibrate_raw_count([[0, 0], [3, 1]], 10) == "1", "a count over the table clamps high"
assert calibrate_raw_count([[10, -4], [14, 6]], 11) == "-3/2", "a negative fraction carries its sign"
assert calibrate_raw_count([[10, -4], [14, 6]], 12) == "1", "a fraction that reduces to a whole"
assert calibrate_raw_count([[10, -4], [14, 6]], 13) == "7/2", "the fraction is put in lowest terms"
assert calibrate_raw_count([[0, 10], [5, 10], [9, 2]], 3) == "10", "a flat segment holds its reading"
assert calibrate_raw_count([[0, 10], [5, 10], [9, 2]], 6) == "8", "the second segment is picked"
assert calibrate_raw_count([[0, 10], [5, 10], [9, 2]], 7) == "6", "a falling segment reads down"
assert calibrate_raw_count([[0, -3], [6, 3]], 3) == "0", "a crossing of nought reads as plain 0"


def rejects(*args):
    try:
        calibrate_raw_count(*args)
    except ValueError:
        return True
    return False


assert rejects("rows", 1), "the table must be a list"
assert rejects([[0, 0]], 1), "one row is not enough"
assert rejects([[0, 0, 0], [5, 5]], 1), "a three-entry row is refused"
assert rejects([[0, 0], [5, 1.5]], 1), "a fractional entry is refused"
assert rejects([[0, 0], [0, 5]], 0), "repeated counts are refused"
assert rejects([[9, 0], [2, 5]], 4), "falling counts are refused"
assert rejects([[0, 0], [5, 1]], 2.5), "a fractional raw count is refused"
assert rejects([[0, 0], [5, 1]], 9000000), "a raw count beyond a million is refused"
assert rejects([[0, 0], [5, 4000000]], 2), "a reading beyond a million is refused"
print("ok")
