from solution import squash_journal

assert squash_journal([]) == [], "empty journal squashes to empty"
assert squash_journal([["put", "a", 1], ["put", "b", 2]]) == [
    ["put", "a", 1],
    ["put", "b", 2],
], "independent puts survive in order"
assert squash_journal([["put", "a", 1], ["put", "a", 5]]) == [
    ["put", "a", 5]
], "overwrite keeps only the final value"
assert squash_journal([["put", "a", 1], ["del", "a"]]) == [], "put then del cancels"
assert squash_journal(
    [["put", "a", 7], ["ren", "a", "b"], ["ren", "b", "c"]]
) == [["put", "c", 7]], "a rename chain collapses to one put of the final name"
assert squash_journal([["put", "a", 1], ["put", "b", 2], ["put", "a", 3]]) == [
    ["put", "b", 2],
    ["put", "a", 3],
], "ordering follows the establishing put, not first appearance"
assert squash_journal(
    [["put", "x", 4], ["put", "y", 9], ["del", "x"], ["ren", "y", "x"]]
) == [["put", "x", 9]], "rename after delete reuses the freed name"
assert squash_journal(
    [["put", "a", 1], ["ren", "a", "b"], ["put", "b", 2]]
) == [["put", "b", 2]], "overwriting a renamed key re-establishes it"
assert squash_journal(
    [
        ["put", "a", 1],
        ["put", "b", 2],
        ["ren", "a", "t"],
        ["ren", "b", "a"],
        ["ren", "t", "b"],
    ]
) == [["put", "b", 1], ["put", "a", 2]], "a swap keeps establishing order"


def rejects(journal):
    try:
        squash_journal(journal)
    except ValueError:
        return True
    return False


assert rejects([["del", "a"]]), "del of absent key"
assert rejects([["ren", "a", "b"]]), "ren of absent source"
assert rejects(
    [["put", "a", 1], ["put", "b", 2], ["ren", "a", "b"]]
), "ren onto existing destination"
assert rejects([["zap", "a"]]), "unknown operation"
assert rejects([["put", "", 1]]), "empty key"
assert rejects([["put", "a", 0]]), "zero value"
assert rejects([["put", "a", True]]), "boolean value"
print("ok")
