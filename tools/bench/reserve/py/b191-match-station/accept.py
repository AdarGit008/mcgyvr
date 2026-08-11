from solution import match_station

names = ["Harbor", "Harbor Annex", "Harborview", "North Harbor", "Depot"]

assert match_station(names, "harbor") == "Harbor", "an exact name beats the names that merely begin with it"
assert match_station(names, "HarborV") == "Harborview", "letter case is ignored on both sides"
assert match_station(names, "harb") == "Harbor", "the shortest name beginning with the fragment wins"
assert match_station(names, "annex") == "Harbor Annex", "a name holding the fragment inside serves when none begins with it"
assert match_station(["Quarry Yard", "Quarry Halt"], "quarry") == "Quarry Halt", "names of equal length break the tie alphabetically"
assert match_station(names, "wharf") is None, "a fragment no name holds resolves to nothing"


def rejects(names, fragment):
    try:
        match_station(names, fragment)
    except ValueError:
        return True
    return False


assert rejects(names, ""), "an empty fragment is rejected"
print("ok")
