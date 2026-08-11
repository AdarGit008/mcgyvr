from solution import apply_edit_script

assert apply_edit_script(
    "hello world", [["copy", 6], ["skip", 5], ["insert", "there"]]
) == "hello there", "replace the tail"
assert apply_edit_script("abcdef", [["skip", 3], ["copy", 3]]) == "def", "drop the head"
assert apply_edit_script("", [["insert", "fresh"]]) == "fresh", "insert into an empty original"


def rejects(*args):
    try:
        apply_edit_script(*args)
    except ValueError:
        return True
    return False


assert rejects(42, []), "non-string original is rejected"
assert rejects("ab", [["paste", "x"], ["copy", 2]]), "unknown op is rejected"
assert rejects("ab", [["copy", 0], ["copy", 2]]), "zero count is rejected"
assert rejects("ab", [["insert", ""], ["copy", 2]]), "empty insert text is rejected"
assert rejects("ab", [["copy", 3]]), "reading past the end is rejected"
assert rejects("ab", [["copy", 1]]), "stopping short is rejected"
print("ok")
