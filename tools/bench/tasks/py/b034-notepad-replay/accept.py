from solution import replay_notepad

assert replay_notepad([]) == "", "no commands leave an empty buffer"
assert replay_notepad([["type", "hello "], ["type", "world"]]) == "hello world", (
    "typed texts concatenate"
)
assert replay_notepad([["type", "carrots"], ["erase", 3]]) == "carr", "erase removes the tail"
assert replay_notepad([["type", "ab"], ["erase", 2]]) == "", "erase may drain the whole buffer"
assert replay_notepad(
    [["type", "one two one"], ["replace", "one", "three"]]
) == "one two three", "replace rewrites the last occurrence"
assert replay_notepad([["type", "draft"], ["undo", 1]]) == "", "undo reverts a type"
assert replay_notepad([["type", "a"], ["type", "b"], ["undo", 2]]) == "", (
    "undo may revert several edits at once"
)
assert replay_notepad([["type", "x"], ["type", "y"], ["undo", 1], ["redo", 1]]) == "xy", (
    "redo re-applies the undone edit"
)
assert replay_notepad([["type", "a"], ["undo", 1], ["type", "b"]]) == "b", (
    "a fresh edit after undo wins"
)
assert replay_notepad([["type", "note"], ["erase", 2], ["undo", 1]]) == "note", (
    "undo restores erased text"
)
assert replay_notepad(
    [
        ["type", "alpha"],
        ["type", " beta"],
        ["replace", "beta", "gamma"],
        ["undo", 1],
        ["redo", 1],
        ["erase", 6],
    ]
) == "alpha", "replace, undo and redo interleave"


def rejects(commands):
    try:
        replay_notepad(commands)
    except ValueError:
        return True
    return False


assert rejects([["poke", "x"]]), "unknown action"
assert rejects([["type", 3]]), "type of a non-string"
assert rejects([["type", ""]]), "type of an empty text"
assert rejects([["type", "ab"], ["erase", 0]]), "erase count of zero"
assert rejects([["type", "ab"], ["erase", 3]]), "erase count exceeding the buffer"
assert rejects([["undo", 1]]), "undo with no edits"
assert rejects([["type", "a"], ["redo", 1]]), "redo with nothing undone"
assert rejects([["type", "a"], ["undo", 1], ["type", "b"], ["redo", 1]]), (
    "redo after a fresh edit"
)
assert rejects([["type", "abc"], ["replace", "zz", "q"]]), "replace of an absent text"
assert rejects([["type", "abc"], ["replace", "", "q"]]), "replace of an empty text"
assert rejects([["erase"]]), "command without its payload"
assert rejects([["type", "a"], ["undo", 0]]), "undo count of zero"
print("ok")
