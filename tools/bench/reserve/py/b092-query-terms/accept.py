from solution import tokenize_query

assert tokenize_query("oak") == [["word", "oak"]], "a lone plain word"
assert tokenize_query("+oak") == [["must", "oak"]], "a required word drops its sign"
assert tokenize_query("-pine") == [["not", "pine"]], "an excluded word drops its sign"
assert tokenize_query('"garden chair"') == [
    ["phrase", "garden chair"]
], "a phrase keeps its inner spaces"
assert tokenize_query('oak +cedar -pine "low table" stool') == [
    ["word", "oak"],
    ["must", "cedar"],
    ["not", "pine"],
    ["phrase", "low table"],
    ["word", "stool"],
], "kinds mix in input order"
assert tokenize_query("  oak   bench ") == [
    ["word", "oak"],
    ["word", "bench"],
], "extra spaces separate nothing"
assert tokenize_query('"a b" "c d"') == [
    ["phrase", "a b"],
    ["phrase", "c d"],
], "phrases back to back stay apart"


def rejects(value):
    try:
        tokenize_query(value)
    except ValueError:
        return True
    return False


assert rejects(42), "a non-string query is rejected"
assert rejects(""), "an empty query is rejected"
assert rejects("   "), "an all-space query is rejected"
assert rejects('"broken'), "an unclosed phrase is rejected"
assert rejects('""'), "an empty phrase is rejected"
assert rejects("+"), "a lone + is rejected"
assert rejects("oak -"), "a dangling - is rejected"
print("ok")
