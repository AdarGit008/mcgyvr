from solution import run_editor

assert run_editor([["type", "ab"], ["type", "cd"]]) == "abcd", "typing appends"
assert run_editor([["type", "hello"], ["erase", 3]]) == "he", "erase drops the tail"
assert run_editor([["type", "ab"], ["undo"]]) == "", "undo reverts a type"
assert (
    run_editor([["type", "ab"], ["type", "cd"], ["undo"], ["undo"], ["redo"]]) == "ab"
), "redo reinstates one undone edit"
assert (
    run_editor([["type", "ab"], ["erase", 1], ["undo"], ["redo"]]) == "a"
), "an erase can be undone and redone"
assert (
    run_editor([["type", "ab"], ["undo"], ["type", "cd"], ["redo"]]) == "cd"
), "a fresh edit makes redo a no-op"
assert (
    run_editor(
        [["type", "ab"], ["type", "cd"], ["undo"], ["type", "xy"], ["redo"], ["redo"]]
    )
    == "abxy"
), "the whole redo history dies at a divergence"
assert run_editor([["undo"], ["redo"], ["type", "a"]]) == "a", "empty history is silent"


def rejects(ops):
    try:
        run_editor(ops)
    except ValueError:
        return True
    return False


assert rejects([["type", "ab"], ["erase", 3]]), "erase past the start is rejected"
assert rejects([["type", "ab"], ["erase", 0]]), "zero erase is rejected"
assert rejects([["paste", "x"]]), "an unknown operation is rejected"
print("ok")
