from solution import format_subscriber_number

assert (
    format_subscriber_number("kv", "123456789") == "0 123 456 789"
), "kv takes a single-figure stem and three blocks of three"
assert (
    format_subscriber_number("mr", "12345678") == "07 1234 5678"
), "mr takes a two-figure stem and two blocks of four"
assert (
    format_subscriber_number("ts", "1234567890") == "+31 12 3456 7890"
), "ts takes a stem with a plus and blocks of two, four and four"
assert (
    format_subscriber_number("wd", "1234567") == "123 4567"
), "wd carries no stem, so the blocks stand alone"
assert (
    format_subscriber_number("kv", "900000001") == "0 900 000 001"
), "noughts inside the run are printed like any other digit"
assert (
    format_subscriber_number("wd", "9876543") == "987 6543"
), "the shortest region still splits three then four"


def rejects(region, digits):
    try:
        format_subscriber_number(region, digits)
    except ValueError:
        return True
    return False


assert rejects("zz", "1234567"), "an unknown region"
assert rejects("KV", "123456789"), "a region in capitals"
assert rejects(7, "1234567"), "a region must be a string"
assert rejects("wd", 1234567), "the digits must be a string"
assert rejects("wd", "123 4567"), "a space inside the run"
assert rejects("wd", "12-4567"), "a dash inside the run"
assert rejects("wd", "12345678"), "one digit too many for wd"
assert rejects("kv", "12345678"), "one digit too few for kv"
assert rejects("wd", ""), "an empty run"
assert rejects("wd", "0123456"), "a run opening with a nought"
print("ok")
