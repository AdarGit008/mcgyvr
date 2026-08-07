from solution import read_tag_attributes

assert read_tag_attributes("[panel]") == {
    "stem": "panel",
    "marks": [],
}, "a bare tag carries no marks"
assert read_tag_attributes("[panel wide id=main]") == {
    "stem": "panel",
    "marks": [
        {"name": "wide", "setting": ""},
        {"name": "id", "setting": "main"},
    ],
}, "a lone name settles to the empty string"
assert read_tag_attributes("""[note text="hello there" sign='a"b']""") == {
    "stem": "note",
    "marks": [
        {"name": "text", "setting": "hello there"},
        {"name": "sign", "setting": 'a"b'},
    ],
}, "the opposite quote means itself inside a fence"
assert read_tag_attributes(r"""[a s="say \"hi\"" b='c\\d']""") == {
    "stem": "a",
    "marks": [
        {"name": "s", "setting": 'say "hi"'},
        {"name": "b", "setting": "c\\d"},
    ],
}, "a backslash means the one character behind it"
assert read_tag_attributes("[a k=1 k=1]") == {
    "stem": "a",
    "marks": [{"name": "k", "setting": "1"}],
}, "the same setting twice folds into one mark"
assert read_tag_attributes('[a k="" j=x]') == {
    "stem": "a",
    "marks": [
        {"name": "k", "setting": ""},
        {"name": "j", "setting": "x"},
    ],
}, "a fenced setting may be empty"
assert read_tag_attributes("[x-1 src=file_name.v2-b]") == {
    "stem": "x-1",
    "marks": [{"name": "src", "setting": "file_name.v2-b"}],
}, "a plain setting spans dots, underscores and hyphens"
assert read_tag_attributes("[row cell='a]b' end]") == {
    "stem": "row",
    "marks": [
        {"name": "cell", "setting": "a]b"},
        {"name": "end", "setting": ""},
    ],
}, "a bracket inside a fence does not close the tag"


def rejects(tag):
    try:
        read_tag_attributes(tag)
    except ValueError:
        return True
    return False


assert rejects(9), "a tag that is not a string is rejected"
assert rejects(""), "an empty tag is rejected"
assert rejects("panel]"), "a missing opening bracket is rejected"
assert rejects("[panel"), "a missing closing bracket is rejected"
assert rejects("[panel] extra"), "text after the closing bracket is rejected"
assert rejects("[]"), "an empty stem is rejected"
assert rejects("[1bad]"), "a stem opening with a digit is rejected"
assert rejects("[a  b]"), "two spaces running are rejected"
assert rejects("[a ]"), "a space before the closing bracket is rejected"
assert rejects("[a Key=1]"), "a capital in a mark name is rejected"
assert rejects("[a =1]"), "an equals sign with no name is rejected"
assert rejects("[a k=]"), "an equals sign with no setting is rejected"
assert rejects('[a k="open]'), "a fence never closed is rejected"
assert rejects(r'[a k="bad\z"]'), "a stray backslash escape is rejected"
assert rejects("[a k=v#w]"), "a stray character after a plain setting is rejected"
assert rejects("[a k=1 k=2]"), "one name with two settings is rejected"
print("ok")
