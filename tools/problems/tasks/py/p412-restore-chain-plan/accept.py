from solution import plan_restore_chain


def run(label, kind, step, sound):
    return {"label": label, "kind": kind, "step": step, "sound": sound}


mixed = [
    run("mon", "full", 0, True),
    run("tue", "incr", 1, True),
    run("wed", "diff", 2, True),
    run("thu", "incr", 3, True),
    run("fri", "incr", 4, True),
]

assert plan_restore_chain(mixed, 0) == {
    "ok": "yes",
    "chain": ["mon"],
    "reason": "",
}, "a full run stands alone"
assert plan_restore_chain(mixed, 1) == {
    "ok": "yes",
    "chain": ["mon", "tue"],
    "reason": "",
}, "an incr run takes whatever sits directly before it"
assert plan_restore_chain(mixed, 2) == {
    "ok": "yes",
    "chain": ["mon", "wed"],
    "reason": "",
}, "a diff run skips straight to the full run"
assert plan_restore_chain(mixed, 4) == {
    "ok": "yes",
    "chain": ["mon", "wed", "thu", "fri"],
    "reason": "",
}, "two incr runs land on the diff and shorten the stack"
assert plan_restore_chain(list(reversed(mixed)), 4) == {
    "ok": "yes",
    "chain": ["mon", "wed", "thu", "fri"],
    "reason": "",
}, "the order the runs arrive in changes nothing"

two_fulls = [
    run("base", "full", 0, True),
    run("cut1", "diff", 1, True),
    run("rest", "full", 2, True),
    run("cut2", "diff", 3, True),
]
assert plan_restore_chain(two_fulls, 3) == {
    "ok": "yes",
    "chain": ["rest", "cut2"],
    "reason": "",
}, "a diff run pairs with the newest full run, not the oldest"

spoilt_full = [
    run("base", "full", 0, True),
    run("rest", "full", 2, False),
    run("cut2", "diff", 3, True),
]
assert plan_restore_chain(spoilt_full, 3) == {
    "ok": "yes",
    "chain": ["base", "cut2"],
    "reason": "",
}, "an unreadable full run is stepped over for an older sound one"

spoilt_middle = [
    run("mon", "full", 0, True),
    run("wed", "diff", 2, False),
    run("thu", "incr", 3, True),
]
assert plan_restore_chain(spoilt_middle, 3) == {
    "ok": "no",
    "chain": [],
    "reason": "damaged",
}, "an incr run cannot step over an unreadable predecessor"
assert plan_restore_chain(spoilt_middle, 2) == {
    "ok": "no",
    "chain": [],
    "reason": "damaged",
}, "a target that is itself unreadable reports damaged"
assert plan_restore_chain([run("only", "diff", 7, True)], 7) == {
    "ok": "no",
    "chain": [],
    "reason": "nofull",
}, "a diff run with nothing before it is unreachable"
assert plan_restore_chain(
    [run("dud", "full", 0, False), run("late", "diff", 1, True)], 1
) == {
    "ok": "no",
    "chain": [],
    "reason": "nofull",
}, "a diff run whose only full run is unreadable is unreachable"
assert plan_restore_chain(
    [run("a", "incr", 4, True), run("b", "incr", 5, True)], 5
) == {
    "ok": "no",
    "chain": [],
    "reason": "nofull",
}, "a walk that runs off the start without a full run is unreachable"


def rejects(one, two):
    try:
        plan_restore_chain(one, two)
    except ValueError:
        return True
    return False


assert rejects([], 0), "an empty list is rejected"
assert rejects("mon", 0), "a string is rejected"
assert rejects([{"label": "mon", "kind": "full", "step": 0}], 0), (
    "a run without sound is rejected"
)
assert rejects([run("", "full", 0, True)], 0), "an empty label is rejected"
assert rejects(
    [run("mon", "full", 0, True), run("mon", "incr", 1, True)], 1
), "a repeated label is rejected"
assert rejects(
    [run("mon", "full", 0, True), run("tue", "incr", 0, True)], 0
), "a repeated step is rejected"
assert rejects([run("mon", "clone", 0, True)], 0), "an unknown kind is rejected"
assert rejects([run("mon", "full", -1, True)], -1), "a negative step is rejected"
assert rejects([run("mon", "full", 0, "yes")], 0), (
    "a sound flag that is a word is rejected"
)
assert rejects([run("mon", "full", 0, True)], True), (
    "a target given as a boolean is rejected"
)
assert rejects(mixed, 9), "a target no run carries is rejected"
assert rejects(mixed, 1.5), "a fractional target is rejected"
print("ok")
