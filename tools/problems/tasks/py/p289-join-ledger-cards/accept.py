from solution import join_ledger_cards

LAYOUT = [
    {"name": "who", "start": 1, "width": 6},
    {"name": "what", "start": 7, "width": 8},
]

assert join_ledger_cards(["=Ann...Tools..."], LAYOUT) == [
    {"who": "Ann", "what": "Tools"}
], "one opening card, packing removed from the right"
assert join_ledger_cards(["=..x...Y......."], LAYOUT) == [
    {"who": "..x", "what": "Y"}
], "full stops that lead a value belong to it"
assert join_ledger_cards(["=Ann...Tools...", "+bury..&nails.."], LAYOUT) == [
    {"who": "Annbury", "what": "Tools&nails"}
], "a carrying card lengthens the open record"
assert join_ledger_cards(
    ["=Ann...Tools...", "+bury..&nails..", "+..st..&wax...."], LAYOUT
) == [
    {"who": "Annbury..st", "what": "Tools&nails&wax"}
], "two carrying cards in succession"
assert join_ledger_cards(["=Bo....Rope....", "+.............."], LAYOUT) == [
    {"who": "Bo", "what": "Rope"}
], "a card of nothing but packing adds nothing"
assert join_ledger_cards(
    ["=Ann...Tools...", "+bury..&nails..", "=Bo....Rope....", "=..x...Y......."],
    LAYOUT,
) == [
    {"who": "Annbury", "what": "Tools&nails"},
    {"who": "Bo", "what": "Rope"},
    {"who": "..x", "what": "Y"},
], "one record per opening card, in the order opened"
assert join_ledger_cards(["=Bo....Rope....spare columns"], LAYOUT) == [
    {"who": "Bo", "what": "Rope"}
], "columns beyond the layout are left alone"
assert join_ledger_cards(["=..done"], [{"name": "solo", "start": 3, "width": 4}]) == [
    {"solo": "done"}
], "a layout may start part way into the body"


def rejects(cards, layout):
    try:
        join_ledger_cards(cards, layout)
    except ValueError:
        return True
    return False


assert rejects(["=abcdef"], []), "an empty layout"
assert rejects([], LAYOUT), "no cards at all"
assert rejects(["+Ann...Tools..."], LAYOUT), "a first card that carries"
assert rejects(["-Ann...Tools..."], LAYOUT), "an unknown marker"
assert rejects(["=Ann"], LAYOUT), "a body cut short"
assert rejects(
    ["=abcdefgh"],
    [{"name": "a", "start": 1, "width": 4}, {"name": "a", "start": 5, "width": 2}],
), "repeated field name"
assert rejects(
    ["=abcdefgh"],
    [{"name": "a", "start": 1, "width": 4}, {"name": "b", "start": 4, "width": 2}],
), "two fields over one column"
assert rejects(["=abcdefgh"], [{"name": "a", "start": 0, "width": 2}]), (
    "a start left of the body"
)
assert rejects([9], LAYOUT), "a card that is not a string"
print("ok")
