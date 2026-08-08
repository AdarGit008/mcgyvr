from solution import stalled_loop_members

assert stalled_loop_members({}) == [], "an empty stall table has no loop"
assert stalled_loop_members({"a": "b"}) == [], "waiting on a running job ends nowhere"
assert stalled_loop_members({"a": "b", "b": "a"}) == [
    "a",
    "b",
], "two jobs waiting on each other are a loop"
assert stalled_loop_members({"tail": "a", "a": "b", "b": "c", "c": "a"}) == [
    "a",
    "b",
    "c",
], "the job queued behind the loop is not a member"
assert stalled_loop_members({"z": "p", "p": "q", "q": "p"}) == [
    "p",
    "q",
], "the walk's starting job need not be on the loop"
assert stalled_loop_members({"x": "y", "y": "x", "m": "n", "n": "m"}) == [
    "m",
    "n",
], "with two loops the smallest name decides, not the table order"
assert stalled_loop_members({"n2": "n1", "n1": "n2"}) == [
    "n1",
    "n2",
], "members come back ascending, not in walk order"
assert stalled_loop_members({"one": "two", "two": "three", "three": "four"}) == [
], "a chain that runs out is no loop"


def rejects(waits):
    try:
        stalled_loop_members(waits)
    except ValueError:
        return True
    return False


assert rejects({"a": "a"}), "a job waiting on itself is rejected"
assert rejects({"": "a"}), "an empty job name is rejected"
assert rejects({"a": 5}), "a non-string wait target is rejected"
assert rejects({"a": ""}), "an empty wait target is rejected"
assert rejects([["a", "b"]]), "a list argument is rejected"
print("ok")
