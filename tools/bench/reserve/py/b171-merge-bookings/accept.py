from solution import merge_bookings

assert merge_bookings("9-11") == "9-11", "a lone slot comes back unchanged"
assert merge_bookings("9-11,10-12") == "9-12", "overlapping slots fuse"
assert merge_bookings("9-11,11-13") == "9-13", "slots touching at an hour fuse"
assert merge_bookings("14-15,9-11") == "9-11,14-15", "the plan comes back sorted by start hour"
assert merge_bookings("9-17,10-11") == "9-17", "a slot inside another is swallowed"
assert merge_bookings("0-24") == "0-24", "a whole-day slot is kept"


def rejects(plan):
    try:
        merge_bookings(plan)
    except Exception:
        return True
    return False


assert rejects(911), "a plan that is not a string is rejected"
assert rejects(""), "an empty plan is rejected"
assert rejects("9to11"), "a slot without a hyphen is rejected"
assert rejects("11-9"), "a slot ending before it starts is rejected"
assert rejects("9-25"), "an hour past 24 is rejected"
print("ok")
