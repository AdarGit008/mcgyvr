from solution import steady_readings


def rejects(readings, spec):
    try:
        steady_readings(readings, spec)
    except ValueError:
        return True
    return False


assert steady_readings([7], {"band": 0, "hold": 1}) == {
    "settled": [7],
    "moved": [],
}, "a lone reading is already steady"
assert steady_readings([4, 5, 3, 6, 4], {"band": 100, "hold": 2}) == {
    "settled": [4, 4, 4, 4, 4],
    "moved": [],
}, "a wide band swallows everything"
assert steady_readings([10, 10, 20, 21, 22, 11, 10], {"band": 2, "hold": 3}) == {
    "settled": [10, 10, 10, 10, 20, 20, 20],
    "moved": [4],
}, "the steady figure takes the reading that opened the challenge"
assert steady_readings([0, 5, 9, 10, 11], {"band": 1, "hold": 2}) == {
    "settled": [0, 0, 0, 9, 9],
    "moved": [3],
}, "a noisy reading far from the opener starts the challenge over"
assert steady_readings([0, 9, 1, 9, 9], {"band": 2, "hold": 2}) == {
    "settled": [0, 0, 0, 0, 9],
    "moved": [4],
}, "a quiet reading throws away the challenge in progress"
assert steady_readings([0, 5, 5, 0], {"band": 0, "hold": 1}) == {
    "settled": [0, 5, 5, 0],
    "moved": [1, 3],
}, "a hold of one moves on the first noisy reading"
assert steady_readings([-5, -4, 4, 5, 6], {"band": 3, "hold": 2}) == {
    "settled": [-5, -5, -5, 4, 4],
    "moved": [3],
}, "negative readings measure distance the same way"
assert steady_readings([0, 8, 8, 8, 8], {"band": 1, "hold": 2}) == {
    "settled": [0, 0, 8, 8, 8],
    "moved": [2],
}, "readings already at the new steady figure are quiet afterwards"
assert steady_readings([0, 4, 4, 8, 8, 12, 12], {"band": 1, "hold": 2}) == {
    "settled": [0, 0, 4, 4, 8, 8, 12],
    "moved": [2, 4, 6],
}, "a staircase moves once per landing"

assert rejects("123", {"band": 1, "hold": 1}), "a reading list that is not a list"
assert rejects([], {"band": 1, "hold": 1}), "an empty reading list is rejected"
assert rejects([1, 2.5], {"band": 1, "hold": 1}), "a reading that is not whole"
assert rejects([1, 2], [1, 2]), "a second argument that is not a mapping"
assert rejects([1, 2], {"band": -1, "hold": 1}), "a negative band is rejected"
assert rejects([1, 2], {"hold": 1}), "a missing band is rejected"
assert rejects([1, 2], {"band": 1, "hold": 0}), "a hold of zero is rejected"

print("ok")
