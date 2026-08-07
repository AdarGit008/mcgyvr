from solution import build_on_call_rota

assert build_on_call_rota(["ana", "bo", "cy"], [[], [], [], [], [], []]) == [
    "ana",
    "bo",
    "cy",
    "ana",
    "bo",
    "cy",
], "an unhindered week cycles the roster"
assert build_on_call_rota(["ana", "bo", "cy"], [["ana"], [], []]) == [
    "bo",
    "ana",
    "cy",
], "a block on the opening shift shuffles the order"
assert build_on_call_rota(["ana", "bo", "cy"], [[], [], [], []]) == [
    "ana",
    "bo",
    "cy",
    "ana",
], "four shifts across three people"
assert build_on_call_rota(
    ["ana", "bo", "cy"], [[], ["ana", "cy"], [], ["bo"], []]
) == ["ana", "bo", "cy", "ana", "bo"], "blocks in the middle still balance out"
assert build_on_call_rota(["ana", "bo"], [[], [], []]) == [
    "ana",
    "bo",
    "ana",
], "the ceiling of two lets ana stand twice"
assert build_on_call_rota(["ana", "bo"], [[]]) == ["ana"], "a lone shift"
assert build_on_call_rota(["ana", "bo"], [[], ["bo"], []]) == [], "impossible rota"
assert build_on_call_rota(["ana"], [[], []]) == [], "no two shifts in a row"
assert build_on_call_rota(["ana", "bo"], [["ana", "bo"]]) == [], "everyone blocked"


def rejects(roster, blocked):
    try:
        build_on_call_rota(roster, blocked)
    except ValueError:
        return True
    return False


assert rejects([], [[]]), "an empty roster is rejected"
assert rejects(["ana", "ana"], [[]]), "a repeated roster name is rejected"
assert rejects(["ana", ""], [[]]), "an empty roster name is rejected"
assert rejects(["ana", "bo"], []), "having no shifts at all is rejected"
assert rejects(["ana", "bo"], [["dee"]]), "blocking a stranger is rejected"
assert rejects(["ana", "bo"], [["ana", "ana"]]), "blocking one name twice is rejected"
assert rejects(["ana", "bo"], ["ana"]), "a blocked entry that is not a list is rejected"
print("ok")
