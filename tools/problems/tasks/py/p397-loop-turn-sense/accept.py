from solution import loop_turn_sense

assert loop_turn_sense([[1, 1], [5, 2], [2, 6]]) == {
    "doubled": 19,
    "sense": "counter",
}, "a slanted triangle whose closing side carries weight"

assert loop_turn_sense([[2, 6], [5, 2], [1, 1]]) == {
    "doubled": 19,
    "sense": "clockwise",
}, "the same triangle listed backwards keeps the ground and flips the word"

assert loop_turn_sense([[0, 0], [4, 0], [0, 3]]) == {
    "doubled": 12,
    "sense": "counter",
}, "a right triangle listed anticlockwise"

assert loop_turn_sense([[0, 0], [0, 3], [4, 0]]) == {
    "doubled": 12,
    "sense": "clockwise",
}, "the same right triangle listed the other way about"

assert loop_turn_sense([[0, 0], [4, 0], [4, 4], [0, 4]]) == {
    "doubled": 32,
    "sense": "counter",
}, "a four-wide square"

assert loop_turn_sense([[-1, -1], [3, -1], [3, 2], [-1, 2]]) == {
    "doubled": 24,
    "sense": "counter",
}, "negative measures pen in ground all the same"

assert loop_turn_sense([[0, 0], [2, 0], [5, 0]]) == {
    "doubled": 0,
    "sense": "flat",
}, "studs strung along one line pen in nothing"

assert loop_turn_sense([[3, 3], [1, 2], [-1, 1]]) == {
    "doubled": 0,
    "sense": "flat",
}, "a slanted line of studs is flat too"


def rejects(*args):
    try:
        loop_turn_sense(*args)
    except ValueError:
        return True
    return False


assert rejects([[0, 0], [1, 1]]), "two studs are not a loop"
assert rejects("loop"), "a non-list is rejected"
assert rejects([[0, 0], [2, 0], [0, 0]]), "a repeated stud is rejected"
assert rejects([[0, 0], [2, 0], [1, 2.5]]), "a fractional measure is rejected"
assert rejects([[0, 0], [20001, 0], [0, 2]]), "an oversized measure is rejected"
print("ok")
