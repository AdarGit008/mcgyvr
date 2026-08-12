from solution import pace_of, pace_list


def rejects(call, *args):
    try:
        call(*args)
    except Exception:
        return True
    return False


assert pace_of(600, 2) == 300, "ten minutes over two kilometres"
assert pace_of(601, 2) == 300, "the remainder is discarded"
assert pace_list(
    [{"seconds": 600, "kilometres": 2}, {"seconds": 300, "kilometres": 1}]
) == [300, 300], "a pace for each leg"
assert pace_list([]) == [], "a run with no legs"
assert rejects(pace_of, 600, 0), "no ground covered is rejected"
assert rejects(pace_list, [{"seconds": 600, "kilometres": 0}]), (
    "and the rejection carries up"
)
print("ok")
