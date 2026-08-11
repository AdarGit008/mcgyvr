from solution import format_clock, leg_arrivals, parse_clock

assert parse_clock("09:05") == 545, "parse_clock reads a morning time"
assert format_clock(545) == "09:05", "format_clock zero-pads both parts"
assert leg_arrivals("10:00", []) == [], "no legs, no arrivals"
assert leg_arrivals("10:00", [[120, 0]]) == [
    ["12:00", 0]
], "one leg lands the same day"
assert leg_arrivals("10:00", [[120, 30], [60, 0]]) == [
    ["12:00", 0],
    ["13:30", 0],
], "a layover delays the next leg"
assert leg_arrivals("23:30", [[45, 0]]) == [
    ["00:15", 1]
], "a leg across midnight counts a day"
assert leg_arrivals("00:00", [[1440, 0], [1500, 0]]) == [
    ["00:00", 1],
    ["01:00", 2],
], "days accumulate over long legs"
assert leg_arrivals("23:00", [[30, 60], [30, 0]]) == [
    ["23:30", 0],
    ["01:00", 1],
], "a layover can carry the journey past midnight"


def rejects(call, *args):
    try:
        call(*args)
    except Exception:
        return True
    return False


assert rejects(parse_clock, "9:05"), "a one-digit hour is rejected"
assert rejects(format_clock, 1440), "a full day of minutes is rejected"
assert rejects(leg_arrivals, "24:00", []), "a bad departure is rejected"
assert rejects(leg_arrivals, "10:00", [[30]]), "a one-item leg is rejected"
assert rejects(leg_arrivals, "10:00", [[0, 5]]), "zero travel is rejected"
assert rejects(leg_arrivals, "10:00", [[30, -1]]), "a negative layover is rejected"
print("ok")
