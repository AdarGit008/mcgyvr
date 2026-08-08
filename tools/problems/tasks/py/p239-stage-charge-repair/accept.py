from solution import charge_stages


def stage(name, *tries):
    return {
        "name": name,
        "tries": [{"secs": secs, "code": code} for secs, code in tries],
    }


def rejects(stages, forgive=1):
    try:
        charge_stages(stages, forgive)
    except ValueError:
        return True
    return False


assert charge_stages([], 1) == [], "an empty pipeline bills nothing"
assert charge_stages([stage("a", (5, "done"))], 1) == [
    {"name": "a", "wall": 5, "billed": 5, "free": 0}
], "a clean run is billed in full"
assert charge_stages([stage("a", (6, "hard"))], 1) == [
    {"name": "a", "wall": 6, "billed": 6, "free": 0}
], "a terminal failure is billed, never forgiven"
assert charge_stages([stage("a", (3, "soft"), (7, "done"))], 1) == [
    {"name": "a", "wall": 10, "billed": 7, "free": 3}
], "the first wobble is on the house"
assert charge_stages([stage("a", (3, "soft"), (4, "soft"), (7, "done"))], 1) == [
    {"name": "a", "wall": 14, "billed": 11, "free": 3}
], "the second wobble is past the allowance and is billed"
assert charge_stages([stage("a", (3, "soft"), (7, "done"))], 0) == [
    {"name": "a", "wall": 10, "billed": 10, "free": 0}
], "forgiving nothing bills every second"
assert charge_stages([stage("a", (3, "soft"), (4, "soft"), (7, "done"))], 5) == [
    {"name": "a", "wall": 14, "billed": 7, "free": 7}
], "an allowance larger than the wobbles leaves no soft second billed"
assert charge_stages(
    [stage("a", (2, "soft"), (2, "done")), stage("b", (5, "soft"), (5, "hard"))],
    1,
) == [
    {"name": "a", "wall": 4, "billed": 2, "free": 2},
    {"name": "b", "wall": 10, "billed": 5, "free": 5},
], "each stage draws on its own allowance"
assert charge_stages([stage("a", (0, "soft"), (0, "done"))], 0) == [
    {"name": "a", "wall": 0, "billed": 0, "free": 0}
], "attempts of no length bill nothing"

assert rejects([stage("a", (1, "done"), (1, "soft"))]), "nothing may run after a done"
assert rejects([stage("a", (1, "hard"), (1, "soft"))]), "nothing may run after a hard"
assert rejects([stage("a", (1, "wobbly"))]), "an unknown code is rejected"
assert rejects([stage("a", (-1, "done"))]), "a negative duration is rejected"
assert rejects([{"name": "a", "tries": []}]), "a stage that ran nothing is rejected"
assert rejects([stage("a", (1, "done")), stage("a", (1, "done"))]), (
    "a repeated stage name is rejected"
)
assert rejects([stage("a", (1, "done"))], -1), "a negative allowance is rejected"
print("ok")
