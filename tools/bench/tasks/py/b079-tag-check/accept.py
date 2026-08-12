from solution import check_line, line_tag

assert check_line("ping~ae") == "ping", "a well-tagged line yields its body"
assert check_line("a~b~41") == "a~b", "the body may itself contain a tilde"
assert check_line("~00") == "", "an empty body verifies"
assert line_tag("ping") == "ae", "the tag is the char-code sum modulo 256 in hex"


def rejects(fn, value):
    try:
        fn(value)
    except Exception:
        return True
    return False


assert rejects(check_line, "ping~41"), "a wrong tag is rejected"
assert rejects(check_line, "ping00"), "a missing separator is rejected"
assert rejects(check_line, "xy"), "a line too short for a tag is rejected"
assert rejects(check_line, 42), "a non-string line is rejected"
assert rejects(line_tag, 7), "a non-string body is rejected"
print("ok")
