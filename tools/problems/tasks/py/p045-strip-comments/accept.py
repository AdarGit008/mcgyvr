from solution import strip_comments

assert strip_comments("a = 1 // note\nb = 2") == "a = 1 \nb = 2", (
    "a line comment vanishes but its newline survives"
)
assert strip_comments('s = "http://x" // real') == 's = "http://x" ', (
    "a marker inside a string literal is not a comment"
)
assert strip_comments("x /* mid */ y") == "x  y", (
    "a block comment on one line is removed"
)
assert strip_comments("a\n/* one\ntwo */\nb") == "a\n\nb", (
    "a block comment spanning lines is removed entirely"
)
assert strip_comments("q /* * */ r") == "q  r", (
    "a stray star inside a block comment does not end it early"
)
assert strip_comments('t = "a\\"b" // c') == 't = "a\\"b" ', (
    "an escaped quote does not close the string"
)
assert strip_comments('p = "x\\\\" // y') == 'p = "x\\\\" ', (
    "a double backslash leaves the closing quote closing"
)
assert strip_comments("const x = 5;\n") == "const x = 5;\n", (
    "comment-free code is untouched"
)
assert strip_comments("// whole line\ncode") == "\ncode", (
    "a full-line comment leaves an empty line"
)


def rejects(value):
    try:
        strip_comments(value)
    except ValueError:
        return True
    return False


assert rejects("/* never ends"), "open block comment raises"
assert rejects('v = "never ends'), "open string raises"
print("ok")
