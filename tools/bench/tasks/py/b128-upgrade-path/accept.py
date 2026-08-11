from solution import vet_upgrade_path

assert vet_upgrade_path("1.4", []) == "1.4", "an empty path keeps the installed tag"
assert vet_upgrade_path("1.4", [{"tag": "1.5", "requires": "1.0"}]) == "1.5", (
    "a single lawful step lands on its tag"
)
assert vet_upgrade_path(
    "1.4",
    [{"tag": "2.0", "requires": "1.4"}, {"tag": "2.1", "requires": "2.0"}],
) == "2.1", "a chain carries the tag step by step"
assert vet_upgrade_path("2.9", [{"tag": "2.10", "requires": "2.0"}]) == "2.10", (
    "a point release past 9 still climbs"
)
assert vet_upgrade_path("9.3", [{"tag": "10.0", "requires": "9.0"}]) == "10.0", (
    "a line jump past 9 still climbs"
)
assert vet_upgrade_path("3.0", [{"tag": "3.1", "requires": "3.0"}]) == "3.1", (
    "a floor met exactly is lawful"
)
assert vet_upgrade_path("0.9", [{"tag": "1.0", "requires": "0.1"}]) == "1.0", (
    "zero parts read as plain numbers"
)


def rejects(installed, steps):
    try:
        vet_upgrade_path(installed, steps)
    except Exception:
        return True
    return False


assert rejects("10.2", [{"tag": "9.9", "requires": "1.0"}]), "a numeric downgrade is refused"
assert rejects("3.1", [{"tag": "3.1", "requires": "3.0"}]), "a step repeating the carried tag is refused"
assert rejects("1.2", [{"tag": "2.0", "requires": "1.5"}]), "an unmet floor is refused"
assert rejects(7, []), "a non-string installed tag is rejected"
assert rejects("1.0", "nope"), "a non-list path is rejected"
assert rejects("1.0", ["2.0"]), "a bare-string step is rejected"
assert rejects("1.0", [{"tag": "2.0"}]), "a step without requires is rejected"
assert rejects("1.0", [{"tag": "2.0.1", "requires": "1.0"}]), "three parts are rejected"
assert rejects("1.0", [{"tag": "2.", "requires": "1.0"}]), "an empty part is rejected"
assert rejects("1.0", [{"tag": "2.x", "requires": "1.0"}]), "stray characters are rejected"
assert rejects("1.0", [{"tag": "2.05", "requires": "1.0"}]), "a leading zero is rejected"
print("ok")
