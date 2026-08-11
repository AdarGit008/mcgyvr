from solution import ordinal_stamp


def rejects(year, day):
    try:
        ordinal_stamp(year, day)
    except Exception:
        return True
    return False


assert ordinal_stamp(2000, 1) == "2000-01-01 Saturday", "the anchor day stamps itself"
assert ordinal_stamp(2024, 60) == "2024-02-29 Thursday", "day 60 of a long year is the extra day"
assert ordinal_stamp(2023, 60) == "2023-03-01 Wednesday", "day 60 of a short year has crossed into March"
assert ordinal_stamp(2023, 365) == "2023-12-31 Sunday", "the last day of a short year"
assert ordinal_stamp(2024, 366) == "2024-12-31 Tuesday", "the last day of a long year"
assert ordinal_stamp(2000, 366) == "2000-12-31 Sunday", "a year divisible by 400 is long"
assert rejects(2023, 366), "day 366 of a short year is rejected"
assert rejects(1999, 1), "a year before the anchor is rejected"
print("ok")
