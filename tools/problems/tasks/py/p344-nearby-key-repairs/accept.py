from solution import nearby_key_repairs

BOARD = {"h": "gyjnb", "o": "ipkl", "n": "bhjm", "e": "wrsd"}


def rejects(*args):
    try:
        nearby_key_repairs(*args)
    except ValueError:
        return True
    return False


assert nearby_key_repairs(
    "hone", ["bone", "hole", "home", "hose", "hire"], BOARD
) == ["home", "bone"], "later place first, and only table neighbours qualify"
assert nearby_key_repairs(
    "wat", ["eat", "sat", "cat", "wit"], {"w": "qeas", "a": "qsz", "t": "ryfg"}
) == ["eat", "sat"], "same place follows the table order"
assert nearby_key_repairs(
    "sat",
    ["wat", "eat", "xat", "zat", "dat"],
    {"s": "awdxz", "a": "qsz", "t": "ryfg"},
) == ["wat", "dat", "xat"], "at most three answers"
assert nearby_key_repairs("cat", ["cat", "bat"], {"c": "xdfv"}) == ["cat"], (
    "a word the dictionary knows is answered alone"
)
assert nearby_key_repairs("bat", ["cat", "bad"], {"b": "vghn"}) == [], (
    "keys absent from the table yield nothing"
)
assert nearby_key_repairs("q", ["w", "a"], {"q": "wa"}) == ["w", "a"], (
    "a one-key word"
)
assert nearby_key_repairs("hone", [], BOARD) == [], "an empty dictionary"

assert rejects("", ["a"], BOARD), "empty typed word"
assert rejects("Cat", ["cat"], BOARD), "uppercase typed"
assert rejects(9, ["cat"], BOARD), "typed not a string"
assert rejects("cat", "cat", BOARD), "dictionary not a list"
assert rejects("cat", ["Cat"], BOARD), "dictionary word cased"
assert rejects("cat", ["cot"], "xdfv"), "table not a mapping"
assert rejects("cat", ["cot"], {"ab": "xd"}), "a two-letter table key"
assert rejects("cat", ["cot"], {"c": "X"}), "a table entry not lowercase"
assert rejects("cat", ["cot"], {"c": "xc"}), "a key neighbouring itself"
assert rejects("cat", ["cot"], {"c": "xx"}), "a repeated neighbour"
print("ok")
