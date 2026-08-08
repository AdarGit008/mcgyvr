from solution import expand_template

assert expand_template("hi ${name}!", {"name": "Ada"}, "error") == "hi Ada!", (
    "simple substitution"
)

assert expand_template(
    "${user.home.city}", {"user": {"home": {"city": "Oslo"}}}, "error"
) == "Oslo", "dotted path descends the nested context"

assert expand_template("${n} items", {"n": 7}, "error") == "7 items", (
    "integer printed in decimal"
)

assert expand_template("cost: $$${n}", {"n": 3}, "error") == "cost: $3", (
    "double dollar is one literal dollar"
)

assert expand_template("${a}", {"a": "${b}"}, "error") == "${b}", (
    "inserted text is never rescanned"
)

assert expand_template("<${gone}>", {}, "keep") == "<${gone}>", (
    "keep policy preserves the delimiters"
)

assert expand_template("<${gone}>", {}, "blank") == "<>", (
    "blank policy inserts nothing"
)

assert expand_template("${a.b}", {"a": "leaf"}, "blank") == "", (
    "a failed mid-path lookup obeys the policy"
)


def rejects(template, context, missing):
    try:
        expand_template(template, context, missing)
    except ValueError:
        return True
    return False


assert rejects("${gone}", {}, "error"), "error policy raises on a missing path"
assert rejects("${a.b}", {"a": "leaf"}, "error"), (
    "descending through a non-mapping is a missing path"
)
assert rejects("price $9", {}, "error"), "a stray dollar is rejected"
assert rejects("${open", {}, "error"), "an unclosed placeholder is rejected"
assert rejects("${a..b}", {"a": {"b": 1}}, "error"), "an empty segment is rejected"
assert rejects("${}", {"": 1}, "error"), "an empty path is rejected"
assert rejects("${flag}", {"flag": True}, "error"), (
    "a boolean value is not printable"
)
assert rejects("${user}", {"user": {"name": "x"}}, "error"), (
    "a mapping value is not printable"
)
assert rejects("x", {}, "silent"), "an unknown policy word is rejected"

print("ok")
