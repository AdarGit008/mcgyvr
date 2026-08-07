from solution import tally_page_terms

assert tally_page_terms(["Carts", "cart", "CART", "dogs", "Dog"], ["cart"]) == {
    "dogs": 1,
    "dog": 1,
}, "the skip list is weighed against the headword, capitals and all"
assert tally_page_terms(["Books", "books", "BOOKS"], []) == {
    "book": 3
}, "entries parting only over capitals share one tally"
assert tally_page_terms(["bus", "gas", "its"], []) == {
    "bus": 1,
    "gas": 1,
    "its": 1,
}, "a short entry holds on to its s"
assert tally_page_terms(["Trees", "trees"], ["tree"]) == {}, "every entry may be skipped"
assert tally_page_terms([], ["a"]) == {}, "no entries make no tallies"
assert tally_page_terms(["Alpha", "alpha"], []) == {
    "alpha": 2
}, "an entry that ends in no s is only folded"
assert tally_page_terms(["press"], []) == {"pres": 1}, "exactly four letters may survive"
assert tally_page_terms(["Mice", "mice", "MICE"], ["mice"]) == {}, (
    "a folded entry the skip list names is passed over"
)
assert tally_page_terms(["Nodes", "node", "NODES"], []) == {
    "node": 3
}, "folding and the lost s meet on the same headword"


def rejects(entries, skips):
    try:
        tally_page_terms(entries, skips)
    except ValueError:
        return True
    return False


assert rejects("cat", []), "a non-list of entries is rejected"
assert rejects([], "cat"), "a non-list skip list is rejected"
assert rejects([5], []), "an entry that is not a string is rejected"
assert rejects([""], []), "an empty entry is rejected"
print("ok")
