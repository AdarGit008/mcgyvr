from solution import run_pour_script


def rejects(capacities, script):
    try:
        run_pour_script(capacities, script)
    except ValueError:
        return True
    return False


assert run_pour_script([3, 5], []) == [0, 0], "an empty script changes nothing"
assert run_pour_script([3, 5], ["fill A"]) == [3, 0], "a fill tops one flask"
assert run_pour_script([3, 5], ["fill B", "pour B A"]) == [
    3,
    2,
], "a pour into a dry flask stops at its capacity"
assert run_pour_script([3, 5], ["fill A", "fill B", "pour A B"]) == [
    3,
    5,
], "a brimming receiver takes nothing"
assert run_pour_script([3, 5], ["fill B", "pour B A", "empty A"]) == [
    0,
    2,
], "an empty leaves the rest untouched"
assert run_pour_script([4, 3, 2], ["fill A", "fill C", "pour A C"]) == [
    4,
    0,
    2,
], "a full receiver blocks the whole transfer"
assert run_pour_script([4, 3, 2], ["fill A", "pour A B", "pour B C"]) == [
    1,
    1,
    2,
], "a chain of pours down the rack"
assert rejects([3, 5], ["tip A"]), "unknown action"
assert rejects([3, 5], ["fill Z"]), "mark past the rack"
assert rejects([3, 5], ["pour A A"]), "pour into itself"
assert rejects([3, 5], ["fill"]), "too few words"
assert rejects([3, 5], ["pour A B C"]), "too many words"
assert rejects([3, 5], [7]), "a line that is not a string"
assert rejects([], ["fill A"]), "an empty rack"
print("ok")
