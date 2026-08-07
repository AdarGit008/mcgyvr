from solution import write_tag_marks

assert write_tag_marks("box", []) == "<box>", "no fields means no spaces at all"
assert (
    write_tag_marks(
        "box",
        [
            ["id", "a1"],
            ["title", "hello world"],
            ["note", 'say "hi"'],
            ["flag", ""],
        ],
    )
    == """<box id=a1 title="hello world" note='say "hi"' flag>"""
), "each field picks its own writing"
assert (
    write_tag_marks("x", [["k", "it's \"both\""]]) == r'''<x k="it's \"both\"">'''
), "both quotes present means the double quote wins and gets escaped"
assert (
    write_tag_marks("x", [["k", r"back\slash"]]) == r'<x k="back\\slash">'
), "a backslash is doubled inside the wrapping"
assert write_tag_marks("x", [["src", "a-b.c"]]) == "<x src=a-b.c>", "hyphens and full stops stay naked"
assert write_tag_marks("x", [["k", "a>b"]]) == '<x k="a>b">', "an angle bracket forces wrapping"
assert write_tag_marks("x", [["k", "on'ly"]]) == '<x k="on\'ly">', "a lone single quote keeps the double quote fence"
assert write_tag_marks("x2", [["a1", ""], ["b2", ""]]) == "<x2 a1 b2>", "two empty texts give two bare keys"


def rejects(label, fields):
    try:
        write_tag_marks(label, fields)
    except ValueError:
        return True
    return False


assert rejects("Box", []), "a capital in the label is rejected"
assert rejects("1x", []), "a label opening with a digit is rejected"
assert rejects(5, []), "a label that is not a string is rejected"
assert rejects("x", "k=v"), "fields that are not a list are rejected"
assert rejects("x", [["k"]]), "a field of one is rejected"
assert rejects("x", ["k=v"]), "a field that is not a list is rejected"
assert rejects("x", [["K", "v"]]), "a capital in a key is rejected"
assert rejects("x", [["", "v"]]), "an empty key is rejected"
assert rejects("x", [["k", 5]]), "a text that is not a string is rejected"
assert rejects("x", [["k", "a"], ["k", "b"]]), "one key arriving twice is rejected"
print("ok")
