from solution import siren_minutes


def raise_ev(at, ident, channel, severity):
    return {"at": at, "kind": "raise", "id": ident, "channel": channel, "severity": severity}


def clear_ev(at, ident):
    return {"at": at, "kind": "clear", "id": ident}


assert siren_minutes([raise_ev(0, "a", "ops", 3)], 10) == [
    ["a", 10]
], "a lone alert sounds until the horizon"
assert siren_minutes([raise_ev(0, "a", "ops", 2), raise_ev(4, "b", "ops", 5)], 10) == [
    ["a", 4],
    ["b", 6],
], "a higher severity takes over its channel"
assert siren_minutes([raise_ev(0, "a", "ops", 3), raise_ev(2, "b", "ops", 3)], 10) == [
    ["a", 10],
    ["b", 0],
], "on a severity tie the earlier raise keeps sounding and the loser reports 0"
assert siren_minutes([raise_ev(0, "a", "east", 1), raise_ev(1, "b", "west", 5)], 5) == [
    ["a", 5],
    ["b", 4],
], "channels sound independently"
assert siren_minutes(
    [raise_ev(0, "a", "ops", 2), raise_ev(2, "b", "ops", 5), clear_ev(6, "b")], 10
) == [["a", 6], ["b", 4]], "clearing the louder alert lets the suppressed one sound again"
assert siren_minutes(
    [raise_ev(0, "a", "ops", 1), clear_ev(3, "a"), raise_ev(5, "a", "ops", 2)], 8
) == [["a", 6]], "a re-raised id accumulates across both activations"
assert siren_minutes([], 5) == [], "no events, no pairs"
assert siren_minutes([raise_ev(0, "z", "one", 2), raise_ev(1, "a", "two", 2)], 3) == [
    ["a", 2],
    ["z", 3],
], "pairs come back sorted by id, not by raise order"


def rejects(events, horizon):
    try:
        siren_minutes(events, horizon)
    except ValueError:
        return True
    return False


assert rejects(
    [raise_ev(0, "a", "ops", 2), raise_ev(1, "a", "ops", 3)], 5
), "raising an active id is rejected"
assert rejects([clear_ev(0, "ghost")], 5), "clearing an inactive id is rejected"
assert rejects(
    [raise_ev(3, "a", "ops", 2), raise_ev(3, "b", "ops", 2)], 5
), "equal event times are rejected"
assert rejects([raise_ev(9, "a", "ops", 2)], 5), "an event past the horizon is rejected"
assert rejects([raise_ev(0, "a", "ops", 6)], 5), "severity 6 is rejected"
assert rejects([{"at": 0, "kind": "ack", "id": "a"}], 5), "an unknown kind is rejected"
assert rejects([raise_ev(0, "a", "ops", 2)], "10"), "a non-integer horizon is rejected"
print("ok")
