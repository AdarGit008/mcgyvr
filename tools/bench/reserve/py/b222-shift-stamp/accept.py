from solution import shift_stamp

assert shift_stamp("09:15", 30) == "09:45", "a move inside the hour"
assert shift_stamp("09:15", 0) == "09:15", "a move of nothing holds the stamp"
assert shift_stamp("09:45", 30) == "10:15", "a move rolls into the next hour"
assert shift_stamp("23:50", 20) == "00:10", "a move past midnight wraps"
assert shift_stamp("00:05", -10) == "23:55", "a backward move wraps the other way"
assert shift_stamp("07:30", -1440) == "07:30", "a whole day back lands on itself"
assert shift_stamp("12:00", 4325) == "12:05", "an offset of several days still wraps"


def rejects(stamp, minutes):
    try:
        shift_stamp(stamp, minutes)
    except Exception:
        return True
    return False


assert rejects("7:05", 5), "a one-digit hour is rejected"
assert rejects("24:00", 5), "an hour above 23 is rejected"
assert rejects("10:60", 5), "a minute above 59 is rejected"
assert rejects(1015, 5), "a stamp that is not a string is rejected"
assert rejects("10:15", 1.5), "a fractional offset is rejected"
print("ok")
