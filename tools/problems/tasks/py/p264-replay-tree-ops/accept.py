from solution import replay_tree_ops

assert replay_tree_ops([]) == [], "no steps leave an empty index"
assert replay_tree_ops(["add:50"]) == [50], "one value is its own root"
assert replay_tree_ops(
    ["add:50", "add:30", "add:70", "add:20", "add:40", "add:60", "add:80"]
) == [50, 30, 20, 40, 70, 60, 80], "a balanced seven value index"
assert replay_tree_ops(
    ["add:50", "add:30", "add:70", "add:20", "add:40", "add:60", "add:80", "drop:20"]
) == [50, 30, 40, 70, 60, 80], "dropping a childless value"
assert replay_tree_ops(
    ["add:50", "add:30", "add:70", "add:20", "add:40", "add:60", "add:80", "drop:30"]
) == [50, 20, 40, 70, 60, 80], "dropping a value with two children pulls up the left side's highest"
assert replay_tree_ops(
    ["add:50", "add:30", "add:70", "add:20", "add:40", "add:60", "add:80", "drop:50"]
) == [40, 30, 20, 70, 60, 80], "dropping the root"
assert replay_tree_ops(["add:5", "add:5", "add:5"]) == [5], "repeat additions change nothing"
assert replay_tree_ops(
    ["add:8", "add:3", "add:10", "add:1", "add:6", "add:4", "add:7", "add:14", "add:13", "drop:8"]
) == [7, 3, 1, 6, 4, 10, 14, 13], "the left side's highest is itself a child of something"
assert replay_tree_ops(
    ["add:-4", "add:-9", "add:0", "add:-2", "drop:-4"]
) == [-9, 0, -2], "negative values sort the ordinary way"
assert replay_tree_ops(["add:1", "add:2", "add:3", "drop:1", "drop:2"]) == [3], "a rightward chain drains"
assert replay_tree_ops(
    ["add:20", "add:10", "add:30", "drop:20", "drop:10", "drop:30"]
) == [], "everything dropped"
assert replay_tree_ops(["add:9", "drop:9", "add:4", "add:2"]) == [4, 2], "an emptied index takes a new root"


def rejects(steps):
    try:
        replay_tree_ops(steps)
    except ValueError:
        return True
    return False


assert rejects("add:5"), "a text argument is not a list"
assert rejects(["add:5", "grow:6"]), "an unknown verb is rejected"
assert rejects(["add:x"]), "a value that is not digits is rejected"
assert rejects(["add"]), "a step with no colon is rejected"
assert rejects([50]), "a step that is not text is rejected"
assert rejects(["drop:5"]), "dropping from an empty index is rejected"
assert rejects(["add:5", "drop:6"]), "dropping an absent value is rejected"
assert rejects(["add:5", "add:7", "drop:5", "drop:5"]), "dropping the same value twice is rejected"
print("ok")
