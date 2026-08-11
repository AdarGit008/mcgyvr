from solution import compare_builds, pick_upgrade

assert pick_upgrade("2.1", ["2.4"]) == "2.4", "a lone newer offer wins"
assert pick_upgrade("2.1", ["2.9", "2.3", "2.4"]) == "2.9", (
    "the newest qualifying offer wins, not the last"
)
assert pick_upgrade("2.4", ["2.4"]) is None, "the installed build is no upgrade"
assert pick_upgrade("2.3", ["2.3.0"]) is None, (
    "the same build written deeper is no upgrade"
)
assert pick_upgrade("2.9.9", ["2.10"]) == "2.10", (
    "positions compare numerically, not by their characters"
)
assert pick_upgrade("2.1", ["3.5", "1.9"]) is None, "other release lines never qualify"
assert pick_upgrade("2.5", ["2.4", "2.1"]) is None, "older offers never qualify"
assert pick_upgrade("2.1", []) is None, "no offers, no upgrade"
assert pick_upgrade("10.2", ["10.2.1", "11.0"]) == "10.2.1", (
    "a two-digit line matches itself only"
)
assert compare_builds("1.10", "1.9") == 1, "ten beats nine"
assert compare_builds("2.3", "2.3.0") == 0, "a trailing zero changes nothing"


def rejects(installed, offers):
    try:
        pick_upgrade(installed, offers)
    except ValueError:
        return True
    return False


assert rejects(7, ["1.2"]), "a non-string install is rejected"
assert rejects("v2.1", ["2.2"]), "a prefixed build is rejected"
assert rejects("1.4", ["01.2"]), "a leading zero is rejected"
assert rejects("2.2", "2.3"), "offers must arrive as a list"
print("ok")
