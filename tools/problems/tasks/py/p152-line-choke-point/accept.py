from solution import line_choke_point

assert line_choke_point([["cut", 1, 12], ["weld", 1, 7], ["paint", 1, 9]]) == {
    "station": "weld",
    "output": 7,
}, "single-machine stations: smallest rate is the choke point"
assert line_choke_point([["cut", 3, 5], ["press", 1, 10]]) == {
    "station": "press",
    "output": 10,
}, "parallel machines multiply: 3x5=15 beats 1x10 even though 5<10"
assert line_choke_point([["a", 2, 6], ["b", 4, 3], ["c", 1, 12]]) == {
    "station": "a",
    "output": 12,
}, "three-way capacity tie keeps the earliest station"
assert line_choke_point([["only", 5, 4]]) == {
    "station": "only",
    "output": 20,
}, "one station is its own choke point"
assert line_choke_point([["fast", 10, 10], ["slow", 2, 2], ["mid", 3, 3]]) == {
    "station": "slow",
    "output": 4,
}, "capacity is machines times rate at every station"


def rejects(value):
    try:
        line_choke_point(value)
    except ValueError:
        return True
    return False


assert rejects([]), "empty line is rejected"
assert rejects([["a", 0, 5]]), "zero machines is rejected"
assert rejects([["a", 2, 2.5]]), "fractional rate is rejected"
assert rejects([["a", 1, 5], ["a", 2, 9]]), "duplicate station name is rejected"
assert rejects([["", 1, 5]]), "empty station name is rejected"
print("ok")
