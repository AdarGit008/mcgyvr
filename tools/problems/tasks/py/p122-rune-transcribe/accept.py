from solution import transcribe_runes

assert transcribe_runes("khora", [["kh", "q"], ["o", "au"]]) == "qaura", "basic pairs"
assert transcribe_runes("schule", [["s", "z"], ["sch", "x"]]) == "zchule", (
    "table order beats pattern length"
)
assert transcribe_runes("aaa", [["a", "ab"]]) == "ababab", "outputs are not rescanned"
assert transcribe_runes("aaa", [["aa", "X"]]) == "Xa", "a match consumes its whole span"
assert transcribe_runes("brim", [["zz", "q"]]) == "brim", "no rule fires anywhere"
assert transcribe_runes("keel", []) == "keel", "empty table is identity"
assert transcribe_runes("ab", [["abc", "Z"]]) == "ab", "pattern must fit before the end"
assert transcribe_runes("", [["a", "b"]]) == "", "empty source"


def rejects(source, table):
    try:
        transcribe_runes(source, table)
    except ValueError:
        return True
    return False


assert rejects("x", [["", "y"]]), "empty pattern is rejected"
assert rejects("", [["", "y"]]), "empty pattern rejected even on empty source"
print("ok")
