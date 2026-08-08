from solution import tally_ballots

assert tally_ballots([]) == {}, "no events, empty tally"

assert tally_ballots(
    [
        {"type": "cast", "voter": "v1", "option": "tea"},
        {"type": "cast", "voter": "v2", "option": "tea"},
        {"type": "cast", "voter": "v3", "option": "coffee"},
    ]
) == {"tea": 2, "coffee": 1}, "standing votes are counted per option"

assert tally_ballots(
    [
        {"type": "cast", "voter": "v1", "option": "tea"},
        {"type": "retract", "voter": "v1"},
    ]
) == {"tea": 0}, "a fully retracted option still appears at zero"

assert tally_ballots(
    [
        {"type": "cast", "voter": "v1", "option": "tea"},
        {"type": "retract", "voter": "v1"},
        {"type": "cast", "voter": "v1", "option": "coffee"},
        {"type": "close"},
    ]
) == {"tea": 0, "coffee": 1}, "a voter may cast again after retracting"


def rejects(events):
    try:
        tally_ballots(events)
    except ValueError:
        return True
    return False


assert rejects(
    [
        {"type": "cast", "voter": "v1", "option": "tea"},
        {"type": "cast", "voter": "v1", "option": "coffee"},
    ]
), "casting over a standing vote is an error"

assert rejects([{"type": "retract", "voter": "v9"}]), (
    "retracting with no standing vote is an error"
)

assert rejects(
    [{"type": "close"}, {"type": "cast", "voter": "v1", "option": "tea"}]
), "casting after close is an error"

assert rejects([{"type": "close"}, {"type": "close"}]), (
    "a second close is an error"
)

assert rejects([{"type": "spoil", "voter": "v1"}]), (
    "an unknown event type is an error"
)

print("ok")
