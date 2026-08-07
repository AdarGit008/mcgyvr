from solution import exam_slot_classes

assert exam_slot_classes([[1, 2, 3], [0], [0], [0]]) == [
    [0],
    [1, 2, 3],
], "one busy exam and three quiet ones"
assert exam_slot_classes([[1], [0, 2], [1, 3], [2]]) == [[1, 3], [0, 2]], "a chain"
assert exam_slot_classes([[1, 2], [0, 2], [0, 1]]) == [
    [0],
    [1],
    [2],
], "three exams all sharing"
assert exam_slot_classes([[], [], []]) == [[0, 1, 2]], "nothing shared"
assert exam_slot_classes([[]]) == [[0]], "a single exam"
assert exam_slot_classes([[1, 4], [0, 2], [1, 3], [2, 4], [0, 3]]) == [
    [0, 2],
    [1, 3],
    [4],
], "an odd ring opens a third sitting"
assert exam_slot_classes([[1, 2, 3], [0, 2], [0, 1], [0]]) == [
    [0],
    [1, 3],
    [2],
], "busiest first"
assert exam_slot_classes([[1], [0], [3], [2]]) == [
    [0, 2],
    [1, 3],
], "two independent pairs"


def rejects(conflicts):
    try:
        exam_slot_classes(conflicts)
    except ValueError:
        return True
    return False


assert rejects([]), "no exams rejected"
assert rejects("e"), "non-list rejected"
assert rejects([[0]]), "self sharing rejected"
assert rejects([[1, 1], [0]]), "the same exam named twice rejected"
assert rejects([[1], []]), "one-sided pair rejected"
assert rejects([[1], [0], [9]]), "an exam that does not exist rejected"
print("ok")
