from solution import tag_count


def rejects(line):
    try:
        tag_count(line)
    except Exception:
        return True
    return False


assert tag_count("<a>") == 1, "one marker"
assert tag_count("<a><b>") == 2, "two markers"
assert tag_count("plain") == 0, "no markers at all"
assert tag_count("") == 0, "an empty line"
assert tag_count("<a") == 0, "an unclosed bracket is not a marker"
assert rejects("a>"), "an unmatched closing bracket is rejected"
print("ok")
