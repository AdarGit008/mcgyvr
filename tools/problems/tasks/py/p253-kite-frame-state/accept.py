from solution import kite_frame_state


def traded(times):
    return ["left", "right"] * times


assert kite_frame_state([]) == {
    "left": 0,
    "right": 0,
    "winner": "",
}, "an unplayed frame is level and live"
assert kite_frame_state(["right", "right", "left"]) == {
    "left": 1,
    "right": 2,
    "winner": "",
}, "every rally is a point for its winner"
assert kite_frame_state(["left"] * 15) == {
    "left": 15,
    "right": 0,
    "winner": "left",
}, "15-0 claims the frame"
assert kite_frame_state(traded(14) + ["left"]) == {
    "left": 15,
    "right": 14,
    "winner": "",
}, "15-14 is one clear, not two, so the frame is live"
assert kite_frame_state(traded(14) + ["left", "left"]) == {
    "left": 16,
    "right": 14,
    "winner": "left",
}, "two clear at or past 15 claims the frame"
assert kite_frame_state(traded(19)) == {
    "left": 19,
    "right": 19,
    "winner": "",
}, "traded rallies never let either side pull two clear"
assert kite_frame_state(traded(19) + ["right"]) == {
    "left": 19,
    "right": 20,
    "winner": "right",
}, "20 claims the frame on a single-point gap"
assert kite_frame_state(traded(19) + ["right", "left", "left", "right"]) == {
    "left": 19,
    "right": 20,
    "winner": "right",
}, "rallies after the claim leave both totals alone"
assert kite_frame_state(["left"] * 15 + ["right", "right"]) == {
    "left": 15,
    "right": 0,
    "winner": "left",
}, "a closed frame absorbs nothing further"


def rejects(value):
    try:
        kite_frame_state(value)
    except ValueError:
        return True
    return False


assert rejects(["left", "up"]), "an unknown side is rejected"
assert rejects(["left"] * 15 + ["middle"]), "an unknown side after the claim is still rejected"
assert rejects("left"), "a string argument is rejected"
print("ok")
