from solution import order_shelf_marks

assert order_shelf_marks(["QA 76.73 p12", "QA 76.9 p1", "QA 76 z3", "B 5.5 a1"]) == [
    "B 5.5 a1",
    "QA 76 z3",
    "QA 76.73 p12",
    "QA 76.9 p1",
], "stack first, then the run, fractions read as decimals"
assert order_shelf_marks(["PR 100 m10", "PR 100 m7", "PR 100 b99"]) == [
    "PR 100 b99",
    "PR 100 m7",
    "PR 100 m10",
], "cutter digits are whole numbers, not decimals"
assert order_shelf_marks(["AB 1 a1", "A 9 z9", "B 1 a1"]) == [
    "A 9 z9",
    "AB 1 a1",
    "B 1 a1",
], "a shorter stack shelves before the longer one it opens"
assert order_shelf_marks(["Z 9 a1", "Z 100 a1", "Z 10 a1"]) == [
    "Z 9 a1",
    "Z 10 a1",
    "Z 100 a1",
], "runs count, they do not spell"
assert order_shelf_marks(["M 3.1 a1", "M 3 a1"]) == [
    "M 3 a1",
    "M 3.1 a1",
], "a bare run shelves ahead of a fractioned one"
assert order_shelf_marks(["QA 1 a1"]) == ["QA 1 a1"], "a batch of one"
assert order_shelf_marks(["TX 714.1234 q9", "TX 714.124 q9"]) == [
    "TX 714.1234 q9",
    "TX 714.124 q9",
], "four fraction digits against three"


def rejects(marks):
    try:
        order_shelf_marks(marks)
    except ValueError:
        return True
    return False


assert rejects([]), "an empty batch is rejected"
assert rejects("QA 1 a1"), "a batch that is not a list is rejected"
assert rejects(["qa 76 p1"]), "a small-letter stack is rejected"
assert rejects(["QA 076 p1"]), "a leading zero in the run is rejected"
assert rejects(["QA 76.10 p1"]), "a fraction finishing on a zero is rejected"
assert rejects(["QA  76 p1"]), "a doubled space is rejected"
assert rejects(["QA 76 P1"]), "a capital cutter letter is rejected"
assert rejects(["QA 76 p"]), "a cutter with no digits is rejected"
assert rejects(["QA 76 p1 2019"]), "a fourth segment is rejected"
assert rejects(["QA 76 p1", "QA 76 p1"]), "the same mark twice is rejected"
assert rejects([76]), "a mark that is not a string is rejected"
print("ok")
