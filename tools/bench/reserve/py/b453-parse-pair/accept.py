from solution import split_once, parse_pair


def rejects(line):
    try:
        parse_pair(line)
    except Exception:
        return True
    return False


assert split_once("a:b") == ["a", "b"], "broken at the colon"
assert split_once("a:b:c") == ["a", "b:c"], "only the first colon breaks"
assert parse_pair(" a : b ") == ["a", "b"], "the spaces are trimmed"
assert parse_pair("a:") == ["a", ""], "an empty value"
assert parse_pair(":b") == ["", "b"], "an empty key"
assert rejects("plain"), "a line with no colon is rejected"
print("ok")
