from solution import pick_snippet

NOTES = [
    "The harbour closes at dusk.",
    "A ripe mango fell near the harbour wall.",
    "Mango season ends soon.",
]


def rejects(query, sentences):
    try:
        pick_snippet(query, sentences)
    except ValueError:
        return True
    return False


assert pick_snippet("ripe mango", NOTES) == NOTES[1], "the sentence covering more query words wins"
assert pick_snippet("RIPE", NOTES) == NOTES[1], "matching ignores case"
assert pick_snippet("season", NOTES) == NOTES[2], "one covered word can be enough"
assert pick_snippet(
    "ripe mango", ["mango mango mango stand", "ripe mango juice"]
) == "ripe mango juice", "distinct coverage beats sheer repetition"
assert pick_snippet(
    "cat", ["The cargo catalog is heavy.", "A cat naps."]
) == "A cat naps.", "only whole words match"
assert pick_snippet(
    "spice", ["The spice market opens early today.", "Spice sells fast."]
) == "Spice sells fast.", "a tie goes to the sentence with fewer words"
assert pick_snippet(
    "lamp", ["Old lamp glows.", "New lamp hums."]
) == "Old lamp glows.", "a full tie falls to the earlier sentence"
assert rejects(42, NOTES), "a non-string query is rejected"
assert rejects("?!", NOTES), "a wordless query is rejected"
assert rejects("dusk", []), "an empty sentence list is rejected"
assert rejects("dusk", "not a list"), "sentences must arrive as a list"
assert rejects("ok", ["ok here", 7]), "a non-string sentence is rejected"
assert rejects("ok", ["ok here", ""]), "an empty sentence is rejected"
assert rejects("quartz", NOTES), "a query nothing matches is rejected"
print("ok")
