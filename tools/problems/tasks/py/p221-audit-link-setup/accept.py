from solution import audit_link_setup


def rec(side, verb, seq):
    return {"side": side, "verb": verb, "seq": seq}


SETUP = [
    rec("caller", "PROBE", 1),
    rec("listener", "READY", 1),
    rec("caller", "KEY", 2),
    rec("listener", "SEAL", 2),
]


def rejects(value):
    try:
        audit_link_setup(value)
    except ValueError:
        return True
    return False


assert (
    audit_link_setup(
        SETUP + [rec("caller", "CLOSE", 3), rec("listener", "CLOSE", 3)]
    )
    == ""
), "a run with no pings is faultless"
assert (
    audit_link_setup(
        SETUP
        + [
            rec("caller", "PING", 3),
            rec("listener", "PONG", 3),
            rec("caller", "CLOSE", 4),
            rec("listener", "CLOSE", 4),
        ]
    )
    == ""
), "one ping and its answer are faultless"
assert (
    audit_link_setup(
        SETUP
        + [
            rec("caller", "PING", 3),
            rec("listener", "PONG", 3),
            rec("caller", "PING", 4),
            rec("listener", "PONG", 4),
            rec("caller", "CLOSE", 5),
            rec("listener", "CLOSE", 5),
        ]
    )
    == ""
), "the counter climbs by one on every caller record"
assert audit_link_setup(SETUP) == "short", "a run that stops after the seal"
assert (
    audit_link_setup(SETUP + [rec("caller", "CLOSE", 3)]) == "short"
), "the listener's CLOSE is still owed"
assert (
    audit_link_setup([rec("caller", "PROBE", 0)]) == "PROBE@1"
), "the probe must carry counter one"
assert (
    audit_link_setup([rec("listener", "PROBE", 1)]) == "PROBE@1"
), "the caller opens the run"
assert (
    audit_link_setup([rec("caller", "PROBE", 1), rec("listener", "READY", 2)])
    == "READY@2"
), "the ready repeats the probe's counter"
assert (
    audit_link_setup(
        [
            rec("caller", "PROBE", 1),
            rec("listener", "READY", 1),
            rec("caller", "KEY", 5),
        ]
    )
    == "KEY@3"
), "the key carries exactly one more"
assert (
    audit_link_setup(SETUP + [rec("listener", "PONG", 3)]) == "PONG@5"
), "a pong with no ping before it"
assert (
    audit_link_setup(SETUP + [rec("caller", "PING", 3), rec("caller", "CLOSE", 4)])
    == "CLOSE@6"
), "the listener owes a pong before the close"
assert (
    audit_link_setup(
        SETUP + [rec("caller", "CLOSE", 3), rec("listener", "CLOSE", 4)]
    )
    == "CLOSE@6"
), "the answering close repeats the counter"
assert (
    audit_link_setup(
        SETUP
        + [
            rec("caller", "CLOSE", 3),
            rec("listener", "CLOSE", 3),
            rec("caller", "PING", 4),
        ]
    )
    == "PING@7"
), "nothing belongs after the run is over"

assert rejects("PROBE"), "a list that is not a list is rejected"
assert rejects([]), "an empty list is rejected"
assert rejects([["caller", "PROBE", 1]]), "a record that is not a mapping is rejected"
assert rejects([rec("relay", "PROBE", 1)]), "an unknown side is rejected"
assert rejects([rec("caller", "HELLO", 1)]), "a verb outside the seven is rejected"
assert rejects([rec("caller", "PROBE", "1")]), "a seq that is not a number is rejected"
assert rejects([rec("caller", "PROBE", 1.5)]), "a seq that is not whole is rejected"

print("ok")
