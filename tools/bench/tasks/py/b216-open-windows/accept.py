from solution import open_windows

assert open_windows("09:00-17:00", ["09:00-12:00"]) == "12:00-17:00", "an appointment at the opening pushes the first free stretch later"
assert open_windows("09:00-17:00", ["10:00-11:00"]) == "09:00-10:00, 11:00-17:00", "an appointment in the middle splits the day in two"
assert open_windows("08:30-09:45", []) == "08:30-09:45", "an empty book leaves the whole span free"
assert open_windows("09:00-17:00", ["13:00-14:00", "10:00-11:00"]) == "09:00-10:00, 11:00-13:00, 14:00-17:00", "appointments are placed in time order however they arrive"
assert open_windows("09:00-12:00", ["09:00-10:00", "10:00-11:00"]) == "11:00-12:00", "appointments that meet exactly leave nothing between them"
assert open_windows("09:00-11:00", ["09:00-10:00", "10:00-11:00"]) == "none", "a span covered end to end reports none"


def rejects(*args):
    try:
        open_windows(*args)
    except Exception:
        return True
    return False


assert rejects("09:00-17:00", ["9:00-10:00"]), "an appointment without a two-digit hour is rejected"
print("ok")
