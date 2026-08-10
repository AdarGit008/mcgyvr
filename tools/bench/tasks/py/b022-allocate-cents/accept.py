from solution import allocate_cents, format_amount, parse_amount

assert allocate_cents(100, [1, 1]) == [50, 50], "even split"
assert allocate_cents(101, [1, 1]) == [51, 50], "tie goes to the earliest"
assert allocate_cents(100, [1, 1, 1]) == [34, 33, 33], "three-way split"
assert allocate_cents(10, [1, 1, 3]) == [2, 2, 6], "exact division"
assert allocate_cents(7, [1, 2]) == [2, 5], "largest remainder wins"
assert allocate_cents(10, [0, 1]) == [0, 10], "zero weight takes nothing"
assert allocate_cents(0, [2, 3]) == [0, 0], "zero total, all zeros"
assert allocate_cents(1, [1, 1, 1]) == [1, 0, 0], "one cent, three shares"


def rejects(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


assert rejects(allocate_cents, 100, []), "empty weights rejected"
assert rejects(allocate_cents, 100, [1, -2]), "negative weight rejected"
assert rejects(allocate_cents, 100, [1, 0.5]), "fractional weight rejected"
assert rejects(allocate_cents, 100, [0, 0]), "zero weight sum rejected"
assert rejects(allocate_cents, -5, [1]), "negative total rejected"
assert parse_amount("12.34") == 1234, "dotted amount parses to cents"
assert parse_amount("7") == 700, "whole amount parses to cents"
assert rejects(parse_amount, "12.3"), "one fraction digit rejected"
assert format_amount(1234) == "12.34", "cents format back to dotted form"
assert format_amount(5) == "0.05", "small amounts keep two digits"
print("ok")
