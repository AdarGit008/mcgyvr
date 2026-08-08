from solution import scan_source

assert scan_source("x = 42") == [
    ["id", "x"],
    ["op", "="],
    ["num", "42"],
], "identifier, assignment, number"
assert scan_source("a<=b") == [
    ["id", "a"],
    ["op", "<="],
    ["id", "b"],
], "two-character operator wins over < then ="
assert scan_source("_tmp2 != done") == [
    ["id", "_tmp2"],
    ["op", "!="],
    ["id", "done"],
], "underscore identifiers and !="
assert scan_source("12abc") == [
    ["num", "12"],
    ["id", "abc"],
], "a digit run then letters is num then id"
assert scan_source("(a||b)&&c") == [
    ["op", "("],
    ["id", "a"],
    ["op", "||"],
    ["id", "b"],
    ["op", ")"],
    ["op", "&&"],
    ["id", "c"],
], "logical operators and parentheses"
assert scan_source("n\t*  n") == [
    ["id", "n"],
    ["op", "*"],
    ["id", "n"],
], "tabs and repeated spaces are skipped"
assert scan_source("") == [], "the empty line has no tokens"
assert scan_source("a==b==c") == [
    ["id", "a"],
    ["op", "=="],
    ["id", "b"],
    ["op", "=="],
    ["id", "c"],
], "consecutive == pairs never merge"


def rejects(value):
    try:
        scan_source(value)
    except ValueError:
        return True
    return False


assert rejects("a ! b"), "a lone ! is rejected"
assert rejects("x@y"), "an unknown character is rejected"
print("ok")
