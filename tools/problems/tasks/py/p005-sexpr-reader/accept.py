from solution import read_sexpr

assert read_sexpr("42") == 42, "bare integer"
assert read_sexpr("-7") == -7, "negative integer"
assert read_sexpr("hello") == "hello", "bare symbol"
assert read_sexpr(" + ") == "+", "operator symbol with padding"
assert read_sexpr("()") == [], "empty list"
assert read_sexpr("(add 1 2)") == ["add", 1, 2], "flat list"
assert read_sexpr("(add 1 (mul -2 30))") == [
    "add",
    1,
    ["mul", -2, 30],
], "nested list"
assert read_sexpr("  ( a\t( b ) )\n") == ["a", ["b"]], "free whitespace"
assert read_sexpr("(- 9 3)") == ["-", 9, 3], "lone minus is a symbol"
assert isinstance(read_sexpr("42"), int), "integers decode as numbers"


def rejects(value):
    try:
        read_sexpr(value)
    except ValueError:
        return True
    return False


assert rejects(""), "empty input is rejected"
assert rejects("   "), "whitespace-only input is rejected"
assert rejects("(a"), "unclosed list is rejected"
assert rejects(")"), "stray close is rejected"
assert rejects("(a) b"), "trailing content is rejected"
assert rejects("(1x)"), "digit-led non-integer is rejected"
assert rejects("(a,b)"), "character outside the set is rejected"
assert rejects(42), "non-string is rejected"
print("ok")
