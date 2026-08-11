from solution import wire_text, wire_value

assert wire_value("cargo") == "s5:cargo", "a text leaf"
assert wire_value("") == "s0:", "empty text still carries its length"
assert wire_value(-32) == "n-32;", "a negative whole number"
assert wire_value([]) == "[]", "the empty list"
assert wire_value(["ab", 4]) == "[s2:abn4;]", "a mixed flat list"
assert wire_value([1, ["x", []], "yz"]) == "[n1;[s1:x[]]s2:yz]", "nesting"
assert wire_text("a:b") == "s3:a:b", "the leaf helper renders alone"


def rejects(value):
    try:
        wire_value(value)
    except ValueError:
        return True
    return False


assert rejects(True), "a boolean is rejected"
assert rejects(1.5), "a fractional number is rejected"
assert rejects(None), "None is rejected"
assert rejects({"a": 1}), "a mapping is rejected"
assert rejects("two\nlines"), "a newline in text is rejected"
print("ok")
