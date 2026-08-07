from solution import apply_inflections

assert (
    apply_inflections("city", [["y", "ies"]]) == "cities"
), "a matched tail is swapped for the replacement"
assert (
    apply_inflections("yummy", [["y", "ies"]]) == "yummies"
), "a suffix also present early in the word must still rewrite the tail"
assert (
    apply_inflections("wayside", [["way", "ways"]]) == "wayside"
), "a rule must not fire when only the middle of the word contains it"
assert (
    apply_inflections("bus", [["s", "ses"], ["us", "i"]]) == "buses"
), "the first matching rule wins over later ones"
assert apply_inflections("ox", [["s", "es"]]) == "ox", "a word no rule matches is unchanged"
assert apply_inflections("ox", [["ox", "oxen"]]) == "oxen", "a suffix may cover the whole word"
assert (
    apply_inflections("analysis", [["sis", "ses"]]) == "analyses"
), "multi-character tails rewrite cleanly"
assert apply_inflections("cat", []) == "cat", "an empty table changes nothing"


def rejects(word, rules):
    try:
        apply_inflections(word, rules)
    except ValueError:
        return True
    return False


assert rejects("cat", [["", "s"]]), "an empty suffix is rejected"
print("ok")
