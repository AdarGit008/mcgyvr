from solution import replay_tessel_match

assert replay_tessel_match([]) == {
    "winner": "",
    "bands": [0, 0],
    "points": [0, 0],
    "serve": "A",
}, "no rallies: A holds the opening serve"
assert replay_tessel_match(["B"]) == {
    "winner": "",
    "bands": [0, 0],
    "points": [0, 0],
    "serve": "B",
}, "the receiver wins the rally but not a point"
assert replay_tessel_match(["B", "B"]) == {
    "winner": "",
    "bands": [0, 0],
    "points": [0, 1],
    "serve": "B",
}, "the new server scores on the next rally"
assert replay_tessel_match(["A"] * 4) == {
    "winner": "",
    "bands": [0, 0],
    "points": [4, 0],
    "serve": "A",
}, "a server holding serve stacks points"
assert replay_tessel_match(["A"] * 7) == {
    "winner": "",
    "bands": [1, 0],
    "points": [0, 0],
    "serve": "B",
}, "7-0 closes the band and hands the serve to the loser"

evened = ["A"] * 6 + ["B"] * 7
assert replay_tessel_match(evened) == {
    "winner": "",
    "bands": [0, 0],
    "points": [6, 6],
    "serve": "B",
}, "six all is not a band"

capped = evened + [
    "B",
    "A", "A",
    "B", "B",
    "A", "A",
    "B", "B",
    "A", "A",
    "B", "B",
]
assert replay_tessel_match(capped) == {
    "winner": "",
    "bands": [0, 1],
    "points": [0, 0],
    "serve": "A",
}, "arriving at 10 takes the band on a one-point lead"

swept = ["A"] * 7 + ["A"] * 8 + ["A"] * 8
assert replay_tessel_match(swept) == {
    "winner": "A",
    "bands": [3, 0],
    "points": [7, 0],
    "serve": "",
}, "three bands decide the match and freeze the closing points"


def rejects(value):
    try:
        replay_tessel_match(value)
    except ValueError:
        return True
    return False


assert rejects(swept + ["B"]), "play past the decision is rejected"
assert rejects(["A", "C"]), "an unknown side is rejected"
assert rejects("AB"), "a string argument is rejected"
assert rejects(None), "a None argument is rejected"
print("ok")
