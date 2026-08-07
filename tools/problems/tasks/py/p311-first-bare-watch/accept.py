from solution import first_bare_watch

DUTY = [
    ["helm", "lookout", "helm"],
    ["helm", "lookout"],
    ["lookout"],
]


def rejects(on_duty, warrants):
    try:
        first_bare_watch(on_duty, warrants)
    except ValueError:
        return True
    return False


assert first_bare_watch(DUTY, [["lookout", "1"]]) == 0, "one lookout stands every watch"
assert (
    first_bare_watch(DUTY, [["helm", "1"], ["lookout", "1"]]) == 3
), "the last watch has nobody at the helm"
assert (
    first_bare_watch(DUTY, [["helm", "2"]]) == 2
), "the second watch musters only one helm"
assert first_bare_watch(DUTY, [["cook", "1"]]) == 1, "no watch carries a cook at all"
assert (
    first_bare_watch([[]], [["helm", "1"]]) == 1
), "a watch with nobody standing is bare"
assert (
    first_bare_watch([["helm"]], [["helm", "1"]]) == 0
), "a single hand answers a single demand"
assert (
    first_bare_watch(
        [["helm", "helm", "helm"], ["helm", "helm", "helm"]], [["helm", "3"]]
    )
    == 0
), "three hands on each of two watches"

assert rejects([], [["helm", "1"]]), "a day with no watches is rejected"
assert rejects("helm", [["helm", "1"]]), "a string is not a duty list"
assert rejects(
    ["helm"], [["helm", "1"]]
), "a watch entry that is not a list is rejected"
assert rejects([["helm", ""]], [["helm", "1"]]), "a blank warrant name is rejected"
assert rejects(DUTY, []), "a standing order with nothing in it is rejected"
assert rejects(
    DUTY, [["helm"]]
), "a standing order row that is not a pair is rejected"
assert rejects(DUTY, [["helm", "two"]]), "a lettered headcount is rejected"
assert rejects(DUTY, [["helm", "0"]]), "a headcount of nought is rejected"
assert rejects(
    DUTY, [["helm", "1"], ["helm", "2"]]
), "one warrant demanded twice is rejected"
print("ok")
