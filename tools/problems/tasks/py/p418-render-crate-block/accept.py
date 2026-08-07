from solution import render_crate_block


def block(*lines):
    return "\n".join(lines)


assert render_crate_block(
    {"size": 3, "name": "kite", "parts": ["rod", 7], "box": {"lid": "tin"}}
) == block(
    "{",
    "..name -> <kite>",
    "..size -> 3",
    "..box ->",
    "....{",
    "......lid -> <tin>",
    "....}",
    "..parts ->",
    "....[",
    "......<rod>",
    "......7",
    "....]",
    "}",
), "flat fields lead, then the deep ones, each group shortest name first"
assert render_crate_block({}) == "{}", "a crate with no fields is two braces"
assert render_crate_block({"b": {}, "a": []}) == block(
    "{", "..a ->", "....[]", "..b ->", "....{}", "}"
), "empty holdings still sit one level deeper than their field"
assert render_crate_block(
    {"zz": 1, "a": "x", "yyy": 2, "bb": {"q": 1}, "c": [1]}
) == block(
    "{",
    "..a -> <x>",
    "..zz -> 1",
    "..yyy -> 2",
    "..c ->",
    "....[",
    "......1",
    "....]",
    "..bb ->",
    "....{",
    "......q -> 1",
    "....}",
    "}",
), "name length decides before the alphabet does"
assert render_crate_block({"bb": 1, "aa": 2}) == block(
    "{", "..aa -> 2", "..bb -> 1", "}"
), "names of equal length fall into alphabetical order"
assert render_crate_block({"row": [{"k": 1}, [2, 3]]}) == block(
    "{",
    "..row ->",
    "....[",
    "......{",
    "........k -> 1",
    "......}",
    "......[",
    "........2",
    "........3",
    "......]",
    "....]",
    "}",
), "a list keeps its own order and nests crates and lists alike"
assert render_crate_block({"t": -5}) == block("{", "..t -> -5", "}"), (
    "a number below zero keeps its hyphen"
)
assert render_crate_block({"t": "a b"}) == block("{", "..t -> <a b>", "}"), (
    "a string is wrapped in angle brackets, spaces and all"
)
assert render_crate_block({"t": ""}) == block("{", "..t -> <>", "}"), (
    "an empty string is a bare pair of angle brackets"
)


def rejects(value):
    try:
        render_crate_block(value)
    except ValueError:
        return True
    return False


assert rejects("hi"), "a string argument is rejected"
assert rejects([1]), "a list argument is rejected"
assert rejects(None), "a None argument is rejected"
assert rejects({"Big": 1}), "a field name with a capital is rejected"
assert rejects({"": 1}), "an empty field name is rejected"
assert rejects({"t": 1.5}), "a number that is not whole is rejected"
assert rejects({"t": True}), "a value that is a boolean is rejected"
assert rejects({"t": None}), "a value that is None is rejected"
assert rejects({"t": "a<b"}), "a string holding an angle bracket is rejected"
assert rejects({"t": "a\nb"}), "a string holding a line break is rejected"
assert rejects({"box": {"Bad": 1}}), "a bad name deep inside is rejected too"
assert rejects({"row": [True]}), "a boolean inside a list is rejected"
print("ok")
