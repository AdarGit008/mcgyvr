from solution import apply_edit_script

assert apply_edit_script("", []) == "", "empty doc and empty script"
assert apply_edit_script("hello", [["keep", "hello"]]) == "hello", (
    "keeping the whole document returns it unchanged"
)
assert apply_edit_script("hello world", [["keep", "hello"], ["drop", " world"]]) == (
    "hello"
), "a drop removes its run"
assert apply_edit_script("ab", [["keep", "a"], ["add", "XY"], ["keep", "b"]]) == (
    "aXYb"
), "an add inserts between kept runs"
assert apply_edit_script("hi", [["keep", "hi"], ["add", "!"]]) == "hi!", (
    "an add after the last kept character appends"
)
assert apply_edit_script("gone", [["drop", "gone"]]) == "", "dropping everything"
assert apply_edit_script("", [["add", "new"], ["add", "file"]]) == "newfile", (
    "adds alone build a document from nothing"
)
assert apply_edit_script(
    "abcdef",
    [["keep", "ab"], ["drop", "cd"], ["add", "Z"], ["keep", "ef"]],
) == "abZef", "keep, drop and add combine into a replacement"


def rejects(doc, script):
    try:
        apply_edit_script(doc, script)
    except ValueError:
        return True
    return False


assert rejects(42, []), "non-string document"
assert rejects("abc", 7), "script is not a list"
assert rejects("a", [["copy", "a"]]), "unknown tag is rejected"
assert rejects("a", [["keep", ""]]), "empty edit text is rejected"
assert rejects("abc", [["keep", "abx"]]), "keep text must match the document"
assert rejects("ab", [["keep", "abc"]]), "an edit past the end is rejected"
assert rejects("abc", [["keep", "a"]]), "unconsumed tail is rejected"
print("ok")
