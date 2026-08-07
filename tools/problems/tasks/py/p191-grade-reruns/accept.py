from solution import grade_reruns

assert grade_reruns([], 2) == [], "an empty log grades nothing"
assert grade_reruns(["a green"], 2) == ["a:solid"], "green first go is solid"
assert grade_reruns(["a red", "a green"], 2) == ["a:shaky"], "red then green is shaky"
assert grade_reruns(["a red", "a red", "a green"], 2) == [
    "a:shaky"
], "two reds then green is still shaky"
assert grade_reruns(["a red", "a red", "a red"], 2) == [
    "a:broken"
], "all reds using every go is broken"
assert grade_reruns(["a red"], 2) == [
    "a:dropped"
], "all reds with goes to spare is dropped"
assert grade_reruns(["a red", "a red"], 2) == [
    "a:dropped"
], "one go short of the budget is still dropped"
assert grade_reruns(["a red"], 0) == [
    "a:broken"
], "with no reruns allowed one red is broken"
assert grade_reruns(["b red", "a green", "b green"], 2) == [
    "a:solid",
    "b:shaky",
], "jobs interleave and come out ordered by name"
assert grade_reruns(["z green", "a red", "a red", "a red"], 2) == [
    "a:broken",
    "z:solid",
], "name order beats arrival order"
assert grade_reruns(["a red", "b red", "a red", "b green"], 1) == [
    "a:broken",
    "b:shaky",
], "a budget of one"


def rejects(log, budget=2):
    try:
        grade_reruns(log, budget)
    except ValueError:
        return True
    return False


assert rejects(["a green", "a red"]), "a go after a green is rejected"
assert rejects(["a red", "a red", "a red", "a red"]), "overspending is rejected"
assert rejects(["a red", "a red"], 0), "overspending a zero budget is rejected"
assert rejects(["a blue"]), "an unknown mark is rejected"
assert rejects(["a"]), "one piece is rejected"
assert rejects(["a red x"]), "three pieces are rejected"
assert rejects([" red"]), "an empty name is rejected"
assert rejects(["a red"], -1), "a negative budget is rejected"
assert rejects(["a red"], "2"), "a non-numeric budget is rejected"
assert rejects("a red"), "a bare string log is rejected"
assert rejects([4]), "a non-string entry is rejected"
print("ok")
