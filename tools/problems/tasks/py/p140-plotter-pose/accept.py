from solution import plotter_pose

assert plotter_pose("F3") == {
    "x": 0,
    "y": 3,
    "facing": "N",
}, "forward from the start heads up the +y axis"
assert plotter_pose("RF2") == {
    "x": 2,
    "y": 0,
    "facing": "E",
}, "a right spin points east and forward follows it"
assert plotter_pose("F1RF1RF1RF1") == {
    "x": 0,
    "y": 0,
    "facing": "W",
}, "a square lap returns home facing west"
assert plotter_pose("B2") == {
    "x": 0,
    "y": -2,
    "facing": "N",
}, "backward moves against the facing without changing it"
assert plotter_pose("LLF3") == {
    "x": 0,
    "y": -3,
    "facing": "S",
}, "two left spins face south"
assert plotter_pose("") == {
    "x": 0,
    "y": 0,
    "facing": "N",
}, "the empty program is the resting pose"
assert plotter_pose("F12L") == {
    "x": 0,
    "y": 12,
    "facing": "W",
}, "distances may span several digits"
assert plotter_pose("LB4") == {
    "x": 4,
    "y": 0,
    "facing": "W",
}, "backward while facing west drifts east"


def rejects(program):
    try:
        plotter_pose(program)
    except ValueError:
        return True
    return False


assert rejects("F0"), "a zero distance is rejected"
assert rejects("F"), "a drive without digits is rejected"
assert rejects("X3"), "an unknown letter is rejected"
assert rejects("f2"), "lowercase commands are rejected"
assert rejects(42), "a non-string program is rejected"
print("ok")
