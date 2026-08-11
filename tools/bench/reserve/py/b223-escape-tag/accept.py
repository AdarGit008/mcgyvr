from solution import escape_tag

assert escape_tag("shelf") == "shelf", "letters stand for themselves"
assert escape_tag("bay-3_A") == "bay-3_A", "digits, hyphens and underscores pass through"
assert escape_tag("row 4") == "row%204", "a space is encoded"
assert escape_tag("50%") == "50%25", "a percent sign is encoded"
assert escape_tag("a/b") == "a%2Fb", "a slash takes uppercase hex digits"
assert escape_tag("\t") == "%09", "a low code is padded to two digits"
assert escape_tag("~") == "%7E", "a tilde is not a safe character"


def rejects(value):
    try:
        escape_tag(value)
    except ValueError:
        return True
    return False


assert rejects(42), "a label that is not a string is rejected"
assert rejects(""), "an empty label is rejected"
assert rejects("café"), "a character past 127 is rejected"
print("ok")
