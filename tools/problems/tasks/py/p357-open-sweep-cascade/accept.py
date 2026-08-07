from solution import open_sweep_cascade

assert open_sweep_cascade(["*---", "----", "----", "---*"], [0, 3]) == {
    "view": ["?100", "1100", "0011", "001?"],
    "opened": 14,
    "struck": False,
}, "a zero square opens the whole of the bare ground"
assert open_sweep_cascade(["*---", "----", "----", "---*"], [3, 3]) == {
    "view": ["????", "????", "????", "???!"],
    "opened": 0,
    "struck": True,
}, "starting on a bomb is struck"
assert open_sweep_cascade(["-"], [0, 0]) == {
    "view": ["0"],
    "opened": 1,
    "struck": False,
}, "one bare square"
assert open_sweep_cascade(["*"], [0, 0]) == {
    "view": ["!"],
    "opened": 0,
    "struck": True,
}, "one square holding a bomb"
assert open_sweep_cascade(["-----", "*****", "-----"], [0, 0]) == {
    "view": ["2????", "?????", "?????"],
    "opened": 1,
    "struck": False,
}, "a square above zero carries the spread no further"
assert open_sweep_cascade(["-----", "-*-*-", "-----", "-----"], [3, 4]) == {
    "view": ["?????", "?????", "11211", "00000"],
    "opened": 10,
    "struck": False,
}, "the spread halts on the ring of digits it opened"
assert open_sweep_cascade(["------", "--*---", "------", "---*--"], [0, 0]) == {
    "view": ["01????", "01????", "012???", "001???"],
    "opened": 10,
    "struck": False,
}, "the spread rounds a bomb without opening it"
assert open_sweep_cascade(["-*-", "---", "-*-"], [1, 1]) == {
    "view": ["???", "?2?", "???"],
    "opened": 1,
    "struck": False,
}, "a lone opened square between two bombs"


def rejects(board, origin):
    try:
        open_sweep_cascade(board, origin)
    except ValueError:
        return True
    return False


assert rejects("--", [0, 0]), "a board that is not a list is thrown out"
assert rejects([], [0, 0]), "a board with no lines is thrown out"
assert rejects([["-"]], [0, 0]), "a line that is not a string is thrown out"
assert rejects(["--", ""], [0, 0]), "an empty line is thrown out"
assert rejects(["--", "---"], [0, 0]), "lines of unequal length are thrown out"
assert rejects(["-x-"], [0, 0]), "a symbol outside star and dash is thrown out"
assert rejects(["---"], [0]), "an origin that is not a pair is thrown out"
assert rejects(["---"], [0, "1"]), "an origin that is not whole is thrown out"
assert rejects(["---"], [0, 3]), "an origin off the board is thrown out"
assert rejects(["---"], [-1, 0]), "an origin above the board is thrown out"
print("ok")
