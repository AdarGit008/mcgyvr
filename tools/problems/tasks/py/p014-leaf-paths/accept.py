from solution import leaf_paths

assert leaf_paths([["root", ""], ["a", "root"], ["b", "root"], ["c", "a"]]) == [
    "root/a/c",
    "root/b",
], "two leaves, one nested"
assert leaf_paths([["only", ""]]) == ["only"], "a lone root is a leaf"
assert leaf_paths([["r", ""], ["m", "r"], ["n", "m"]]) == ["r/m/n"], (
    "a chain yields one path"
)
assert leaf_paths([["c", "a"], ["root", ""], ["a", "root"], ["b", "root"]]) == [
    "root/a/c",
    "root/b",
], "row order does not matter"
assert leaf_paths([["r", ""], ["z", "r"], ["a", "r"]]) == ["r/a", "r/z"], (
    "paths come back sorted"
)


def rejects(rows):
    try:
        leaf_paths(rows)
    except ValueError:
        return True
    return False


assert rejects([["r", ""], ["a", "r"], ["a", "r"]]), "duplicated id rejected"
assert rejects([["r", ""], ["a", "ghost"]]), "unknown parent rejected"
assert rejects([["r", ""], ["s", ""]]), "two roots rejected"
assert rejects([["a", "b"], ["b", "a"]]), "no root rejected"
assert rejects([]), "empty input rejected"
assert rejects([["r", ""], ["a", "b"], ["b", "a"]]), "rows off the root rejected"
print("ok")
