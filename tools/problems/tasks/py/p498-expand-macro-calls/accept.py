from solution import expand_macro_calls

book = [
    {"name": "greet", "arity": 1, "body": "hello #1!"},
    {"name": "pair", "arity": 2, "body": "[#1|#2]"},
    {"name": "dash", "arity": 0, "body": "--"},
    {"name": "twice", "arity": 1, "body": "#1#1"},
    {"name": "loop", "arity": 0, "body": "@loop"},
    {"name": "hash", "arity": 0, "body": "##"},
    {"name": "bad", "arity": 1, "body": "#2"},
]

assert expand_macro_calls(book, "@greet{world}", 3) == "hello world!", "one argument fills one place"
assert expand_macro_calls(book, "@dash", 3) == "--", "a bare name calls a macro of no arity"
assert expand_macro_calls(book, "@pair{a|b}", 3) == "[a|b]", "a bar parts two arguments"
assert expand_macro_calls(book, "@twice{@dash}", 3) == "----", "the filled body is walked again"
assert expand_macro_calls(book, "@@ and @dash", 3) == "@ and --", "doubled at signs stand for one"
assert expand_macro_calls(book, "@hash", 3) == "#", "doubled hashes stand for one"
assert (
    expand_macro_calls(book, "@greet{@greet{x}}", 3) == "hello hello x!!"
), "a call may stand inside an argument"
assert (
    expand_macro_calls(book, "@greet{a{b|c}d}", 3) == "hello a{b|c}d!"
), "a bar buried in braces parts nothing"
assert expand_macro_calls(book, "@greet{}", 3) == "hello !", "empty braces carry one empty argument"
assert (
    expand_macro_calls(book, "plain text | with } odd # marks", 3)
    == "plain text | with } odd # marks"
), "text outside a call is copied across"
assert expand_macro_calls(book, "", 3) == "", "an empty source walks to nothing"
assert expand_macro_calls(book, "@twice{@twice{x}}", 3) == "xxxx", "two nested doublings"
assert expand_macro_calls(book, "@dash", 1) == "--", "a bound of one allows one step"


def rejects(*args):
    try:
        expand_macro_calls(*args)
    except ValueError:
        return True
    return False


assert rejects(book, "@nope", 3), "an undeclared macro is refused"
assert rejects(book, "@greet{a|b}", 3), "two arguments for an arity of one are refused"
assert rejects(book, "@dash{}", 3), "one argument for an arity of nought is refused"
assert rejects(book, "@greet{a", 3), "an unclosed brace is refused"
assert rejects(book, "@", 3), "a trailing at sign is refused"
assert rejects(book, "@1x", 3), "a name opening with a digit is refused"
assert rejects(book, "@bad{x}", 3), "a body reaching past its arity is refused"
assert rejects(book, "@twice{@dash}", 1), "a nested call under a bound of one is refused"
assert rejects(book, "@loop", 5), "a macro calling itself is refused"
assert rejects("no", "x", 3), "the macros must be a list"
assert rejects([7], "x", 3), "a macro must be a record"
assert rejects([{"name": "a", "arity": 0}], "x", 3), "a macro missing a key is refused"
assert rejects([{"name": "A", "arity": 0, "body": ""}], "x", 3), "a capital in a name is refused"
assert rejects(
    [{"name": "a", "arity": 0, "body": ""}, {"name": "a", "arity": 1, "body": "#1"}], "x", 3
), "a repeated name is refused"
assert rejects([{"name": "a", "arity": 10, "body": ""}], "x", 3), "an arity of ten is refused"
assert rejects([{"name": "a", "arity": 0, "body": 5}], "x", 3), "a body that is not a string is refused"
assert rejects(book, 5, 3), "a source that is not a string is refused"
assert rejects(book, "x", 0), "a bound of nought is refused"
print("ok")
