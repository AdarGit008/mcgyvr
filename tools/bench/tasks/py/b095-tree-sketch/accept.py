from solution import draw_tree_lines

assert draw_tree_lines({"name": "attic", "children": []}) == ["attic"], "a lone root is one line"
assert draw_tree_lines(
    {"name": "attic", "children": [{"name": "box", "children": []}]}
) == ["attic", "'-- box"], "an only child takes the closing connector"
assert draw_tree_lines(
    {
        "name": "attic",
        "children": [{"name": "box", "children": []}, {"name": "trunk", "children": []}],
    }
) == ["attic", "|-- box", "'-- trunk"], "only the last child closes its branch"
assert draw_tree_lines(
    {
        "name": "attic",
        "children": [
            {"name": "box", "children": [{"name": "photos", "children": []}]},
            {"name": "trunk", "children": []},
        ],
    }
) == [
    "attic",
    "|-- box",
    "|   '-- photos",
    "'-- trunk",
], "an open branch keeps its bar in front of deeper lines"
assert draw_tree_lines(
    {
        "name": "attic",
        "children": [
            {"name": "box", "children": []},
            {"name": "trunk", "children": [{"name": "coats", "children": []}]},
        ],
    }
) == ["attic", "|-- box", "'-- trunk", "    '-- coats"], "a closed branch indents with spaces"
assert draw_tree_lines(
    {
        "name": "a",
        "children": [
            {
                "name": "b",
                "children": [
                    {"name": "c", "children": [{"name": "d", "children": []}]}
                ],
            }
        ],
    }
) == [
    "a",
    "'-- b",
    "    '-- c",
    "        '-- d",
], "a chain of only children steps four spaces per level"
assert draw_tree_lines(
    {
        "name": "root",
        "children": [
            {
                "name": "src",
                "children": [
                    {"name": "app", "children": [{"name": "main", "children": []}]},
                    {"name": "lib", "children": []},
                ],
            },
            {"name": "docs", "children": [{"name": "guide", "children": []}]},
        ],
    }
) == [
    "root",
    "|-- src",
    "|   |-- app",
    "|   |   '-- main",
    "|   '-- lib",
    "'-- docs",
    "    '-- guide",
], "bars trace exactly the branches still open"


def rejects(root):
    try:
        draw_tree_lines(root)
    except ValueError:
        return True
    return False


assert rejects({"name": "", "children": []}), "an empty name is rejected"
assert rejects({"name": 7, "children": []}), "a numeric name is rejected"
assert rejects({"name": "att\nic", "children": []}), "a name spanning lines is rejected"
assert rejects({"name": "attic", "children": None}), "children must be a list"
assert rejects(
    {"name": "attic", "children": [{"name": "", "children": []}]}
), "a bad node deep in the tree is rejected"
print("ok")
