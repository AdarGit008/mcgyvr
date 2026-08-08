from solution import phrase_quantity_ledger

L = {"0": "no", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five"}
SHORT = {"0": "none", "1": "a", "2": "both"}


def rejects(entries, lexicon):
    try:
        phrase_quantity_ledger(entries, lexicon)
    except ValueError:
        return True
    return False


assert phrase_quantity_ledger([[2, "kite", "kites"]], L) == "two kites", "a single stock"
assert (
    phrase_quantity_ledger([[1, "kite", "kites"]], L) == "one kite"
), "a stock of one takes the one wording"
assert (
    phrase_quantity_ledger([[0, "kite", "kites"]], L) == "nothing at all"
), "a stock of nought is thrown away"
assert phrase_quantity_ledger([], L) == "nothing at all", "an empty ledger"
assert (
    phrase_quantity_ledger([[2, "kite", "kites"], [3, "drum", "drums"]], L)
    == "two kites and three drums"
), "two stocks are tied by and"
assert (
    phrase_quantity_ledger(
        [[1, "kite", "kites"], [1, "drum", "drums"], [4, "flag", "flags"]], L
    )
    == "one kite, one drum, and four flags"
), "three stocks take commas and a closing and"
assert (
    phrase_quantity_ledger(
        [[2, "kite", "kites"], [3, "drum", "drums"], [3, "kite", "kites"]], L
    )
    == "five kites and three drums"
), "a repeated wording folds into its first position"
assert (
    phrase_quantity_ledger([[0, "kite", "kites"], [1, "kite", "kites"]], L) == "one kite"
), "a fold landing on one takes the one wording"
assert (
    phrase_quantity_ledger(
        [[0, "kite", "kites"], [0, "kite", "kites"], [2, "drum", "drums"]], L
    )
    == "two drums"
), "a fold landing on nought is thrown away"
assert (
    phrase_quantity_ledger([[7, "kite", "kites"]], L) == "7 kites"
), "a tally past the lexicon is written in figures"
assert (
    phrase_quantity_ledger([[4, "kite", "kites"], [4, "kite", "kites"]], L) == "8 kites"
), "a fold may carry the tally past the lexicon"
assert (
    phrase_quantity_ledger([[1, "kite", "kites"], [2, "drum", "drums"]], SHORT)
    == "a kite and both drums"
), "the lexicon alone decides the tally words"
assert (
    phrase_quantity_ledger(
        [[1, "ox", "oxen"], [2, "hen", "hens"], [3, "cat", "cats"], [1, "dog", "dogs"]],
        L,
    )
    == "one ox, two hens, three cats, and one dog"
), "four stocks keep their first-seen order"

assert rejects([[2, "kite"]], L), "a line that is not a triple is refused"
assert rejects([[1000, "kite", "kites"]], L), "a tally over 999 is refused"
assert rejects([[-1, "kite", "kites"]], L), "a tally under nought is refused"
assert rejects([[2.5, "kite", "kites"]], L), "a fractional tally is refused"
assert rejects([[2, "", "kites"]], L), "an empty wording is refused"
assert rejects([[2, "kite9", "kites"]], L), "a wording with a figure in it is refused"
assert rejects([[2, "kite", "Kites"]], L), "a wording with a capital is refused"
assert rejects(
    [[1, "kite", "kites"], [2, "kite", "kiten"]], L
), "two many wordings for one stock are refused"
assert rejects([[1, "kite", "kites"]], {"1": "one"}), "a lexicon not starting at 0 is refused"
assert rejects([[1, "kite", "kites"]], {"0": "no", "2": "two"}), "a gap in the lexicon is refused"
assert rejects([[1, "kite", "kites"]], {"0": "no"}), "a lexicon stopping at 0 is refused"
assert rejects(
    [[1, "kite", "kites"]], {"0": "No", "1": "one"}
), "a lexicon word with a capital is refused"
assert rejects([[1, "kite", "kites"]], ["no", "one"]), "a lexicon that is not a mapping is refused"
print("ok")
