from solution import render_lookup_tree

assert render_lookup_tree([], []) == ".", "nothing planted draws a lone dot"
assert render_lookup_tree([7], []) == "[7|.|.]", "a single cell"
assert render_lookup_tree([7, 3, 9], []) == "[7|[3|.|.]|[9|.|.]]", "two leaves under a root"
assert render_lookup_tree([7, 3, 9], [3]) == "[7|.|[9|.|.]]", "pulling a leaf"
assert render_lookup_tree([7, 3, 9, 1, 5], [3]) == "[7|[5|[1|.|.]|.]|[9|.|.]]", (
    "pulling a cell whose high side is a single value"
)
assert render_lookup_tree([7, 3, 9, 8, 12, 10], [9]) == "[7|[3|.|.]|[10|[8|.|.]|[12|.|.]]]", (
    "the stand-in comes from deeper in the high side"
)
assert render_lookup_tree([7, 3, 9, 8, 12, 10], [7]) == "[8|[3|.|.]|[9|.|[12|[10|.|.]|.]]]", (
    "pulling the root"
)
assert render_lookup_tree([50, 30, 70, 60, 65, 80], [50]) == "[60|[30|.|.]|[70|[65|.|.]|[80|.|.]]]", (
    "the stand-in leaves a child behind it"
)
assert render_lookup_tree([10, 5, 15, 12, 20, 11, 13], [10]) == "[11|[5|.|.]|[15|[12|.|[13|.|.]]|[20|.|.]]]", (
    "a deeper stand-in with a high child of its own"
)
assert render_lookup_tree([-3, -8, 0, -5], [-3]) == "[0|[-8|.|[-5|.|.]]|.]", (
    "negative values plant and pull alike"
)
assert render_lookup_tree([4, 4, 4, 2], []) == "[4|[2|.|.]|.]", "repeats of a planted value are ignored"
assert render_lookup_tree([5, 2, 8], [5, 2, 8]) == ".", "pulling everything empties the tree"


def rejects(planted, pulled):
    try:
        render_lookup_tree(planted, pulled)
    except ValueError:
        return True
    return False


assert rejects(7, []), "a first argument that is not a list"
assert rejects([7], "3"), "a second argument that is not a list"
assert rejects([7, 1.5], []), "a fractional planted value"
assert rejects(["7"], []), "a planted value that is text"
assert rejects([7, 3], [9]), "pulling a value never planted"
assert rejects([7, 3], [3, 3]), "pulling the same value twice"
assert rejects([], [1]), "pulling from an empty tree"
print("ok")
