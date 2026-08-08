from solution import fold_machine

SOUND = {
    "alphabet": ["a"],
    "states": ["s0", "s1"],
    "start": "s0",
    "accepting": ["s1"],
    "moves": [["s0", "a", "s1"], ["s1", "a", "s0"]],
}


def bent(patch):
    machine = dict(SOUND)
    machine.update(patch)
    return machine


def rejects(machine):
    try:
        fold_machine(machine)
    except ValueError:
        return True
    return False


assert fold_machine(SOUND) == {
    "size": 2,
    "start": 0,
    "accepting": [1],
    "moves": [[0, "a", 1], [1, "a", 0]],
}, "a machine already at its smallest comes back renumbered"

assert fold_machine(
    {
        "alphabet": ["a"],
        "states": ["p", "q", "r"],
        "start": "p",
        "accepting": ["q", "r"],
        "moves": [["p", "a", "q"], ["q", "a", "q"], ["r", "a", "r"]],
    }
) == {
    "size": 2,
    "start": 0,
    "accepting": [1],
    "moves": [[0, "a", 1], [1, "a", 1]],
}, "a state nothing reaches simply goes"

assert fold_machine(
    {
        "alphabet": ["a"],
        "states": ["x", "y"],
        "start": "x",
        "accepting": ["y"],
        "moves": [["x", "a", "x"], ["y", "a", "y"]],
    }
) == {
    "size": 1,
    "start": 0,
    "accepting": [],
    "moves": [[0, "a", 0]],
}, "when the only survivor accepts nothing the accepting list is empty"

assert fold_machine(
    {
        "alphabet": ["a", "b"],
        "states": ["m", "n"],
        "start": "m",
        "accepting": ["m", "n"],
        "moves": [
            ["m", "a", "n"],
            ["m", "b", "m"],
            ["n", "a", "m"],
            ["n", "b", "n"],
        ],
    }
) == {
    "size": 1,
    "start": 0,
    "accepting": [0],
    "moves": [[0, "a", 0], [0, "b", 0]],
}, "two states nothing tells apart collapse into one"

assert fold_machine(
    {
        "alphabet": ["a", "b"],
        "states": ["S0", "S1", "S2", "S3"],
        "start": "S0",
        "accepting": ["S1", "S3"],
        "moves": [
            ["S0", "a", "S1"],
            ["S0", "b", "S2"],
            ["S1", "a", "S1"],
            ["S1", "b", "S2"],
            ["S2", "a", "S3"],
            ["S2", "b", "S2"],
            ["S3", "a", "S3"],
            ["S3", "b", "S2"],
        ],
    }
) == {
    "size": 2,
    "start": 0,
    "accepting": [1],
    "moves": [[0, "a", 1], [0, "b", 0], [1, "a", 1], [1, "b", 0]],
}, "four states fold to the two the language really needs"

assert fold_machine(
    {
        "alphabet": ["a"],
        "states": ["q0", "q1", "q2", "q3"],
        "start": "q0",
        "accepting": ["q3"],
        "moves": [
            ["q0", "a", "q1"],
            ["q1", "a", "q2"],
            ["q2", "a", "q3"],
            ["q3", "a", "q3"],
        ],
    }
) == {
    "size": 4,
    "start": 0,
    "accepting": [3],
    "moves": [[0, "a", 1], [1, "a", 2], [2, "a", 3], [3, "a", 3]],
}, "states only a long run tells apart must survive the folding"

assert fold_machine(
    {
        "alphabet": ["b", "a"],
        "states": ["s", "x", "y"],
        "start": "s",
        "accepting": ["x"],
        "moves": [
            ["s", "b", "x"],
            ["s", "a", "y"],
            ["x", "a", "x"],
            ["x", "b", "x"],
            ["y", "a", "y"],
            ["y", "b", "y"],
        ],
    }
) == {
    "size": 3,
    "start": 0,
    "accepting": [1],
    "moves": [
        [0, "b", 1],
        [0, "a", 2],
        [1, "b", 1],
        [1, "a", 1],
        [2, "b", 2],
        [2, "a", 2],
    ],
}, "numbering and move order follow the alphabet as it was listed"

assert rejects(bent({"alphabet": []})), "an empty alphabet is rejected"
assert rejects(bent({"alphabet": ["a", "a"]})), "a repeated symbol is rejected"
assert rejects(bent({"states": []})), "an empty state list is rejected"
assert rejects(bent({"states": ["s0", "s0", "s1"]})), "a repeated state is rejected"
assert rejects(bent({"start": "nowhere"})), "a start nobody declared is rejected"
assert rejects(bent({"accepting": ["ghost"]})), "an undeclared acceptor is rejected"
assert rejects(
    bent({"accepting": ["s1", "s1"]})
), "an accepting name listed twice is rejected"
assert rejects(
    bent({"moves": [["s0", "z", "s1"], ["s1", "a", "s0"]]})
), "a move on an undeclared symbol is rejected"
assert rejects(
    bent({"moves": [["s0", "a", "s9"], ["s1", "a", "s0"]]})
), "a move onto an undeclared state is rejected"
assert rejects(
    bent({"moves": [["s0", "a", "s1"]]})
), "a state with no move on a symbol is rejected"
assert rejects(
    bent({"moves": [["s0", "a", "s1"], ["s0", "a", "s0"], ["s1", "a", "s0"]]})
), "a state with two moves on one symbol is rejected"

print("ok")
