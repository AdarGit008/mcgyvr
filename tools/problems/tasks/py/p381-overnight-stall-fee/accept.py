from solution import overnight_stall_fee

board = {"firstHour": 300, "laterHour": 200, "dayCap": 1200, "nightFee": 500}
free_board = {"firstHour": 0, "laterHour": 0, "dayCap": 0, "nightFee": 0}
capped_flat = {"firstHour": 300, "laterHour": 200, "dayCap": 0, "nightFee": 500}

assert overnight_stall_fee(600, 30, board) == {
    "days": [300],
    "nights": 0,
    "total": 300,
}, "half an hour is charged as a whole one"
assert overnight_stall_fee(600, 61, board) == {
    "days": [500],
    "nights": 0,
    "total": 500,
}, "a minute past the hour begins the second one"
assert overnight_stall_fee(600, 120, board) == {
    "days": [500],
    "nights": 0,
    "total": 500,
}, "two whole hours are still two hours"
assert overnight_stall_fee(600, 121, board) == {
    "days": [700],
    "nights": 0,
    "total": 700,
}, "and a minute more begins a third"
assert overnight_stall_fee(600, 480, board) == {
    "days": [1200],
    "nights": 0,
    "total": 1200,
}, "a long daytime stand is trimmed to the cap"
assert overnight_stall_fee(120, 60, board) == {
    "days": [800],
    "nights": 1,
    "total": 800,
}, "standing at two in the morning draws the night fee"
assert overnight_stall_fee(60, 1, board) == {
    "days": [800],
    "nights": 1,
    "total": 800,
}, "one in the morning is inside the night stretch"
assert overnight_stall_fee(59, 1, board) == {
    "days": [300],
    "nights": 0,
    "total": 300,
}, "the minute before it is not"
assert overnight_stall_fee(299, 1, board) == {
    "days": [800],
    "nights": 1,
    "total": 800,
}, "the last minute before five still counts"
assert overnight_stall_fee(300, 1, board) == {
    "days": [300],
    "nights": 0,
    "total": 300,
}, "five o'clock itself does not"
assert overnight_stall_fee(1410, 120, board) == {
    "days": [300, 1000],
    "nights": 1,
    "total": 1300,
}, "a stand across midnight is weighed as two days"
assert overnight_stall_fee(0, 1440, board) == {
    "days": [1700],
    "nights": 1,
    "total": 1700,
}, "the night fee rides on top of a trimmed day"
assert overnight_stall_fee(1380, 2880, board) == {
    "days": [300, 1700, 1700],
    "nights": 2,
    "total": 3700,
}, "three days, two of them holding a night"
assert overnight_stall_fee(600, 30, free_board) == {
    "days": [0],
    "nights": 0,
    "total": 0,
}, "a board of nothing charges nothing"
assert overnight_stall_fee(120, 60, capped_flat) == {
    "days": [500],
    "nights": 1,
    "total": 500,
}, "a cap of nothing still leaves the night fee standing"
assert overnight_stall_fee(4320, 60, board) == {
    "days": [300],
    "nights": 0,
    "total": 300,
}, "a day well past the first is weighed the same way"


def rejects(entry, minutes, sheet):
    try:
        overnight_stall_fee(entry, minutes, sheet)
    except ValueError:
        return True
    return False


assert rejects(600, 0, board), "a stand of no minutes is refused"
assert rejects(600, 10081, board), "a stand past the ceiling is refused"
assert rejects(600, 30.5, board), "a fractional stand is refused"
assert rejects(-1, 30, board), "an entry below nothing is refused"
assert rejects(600, 30, {**board, "nightFee": -1}), "a night fee below nothing is refused"
assert rejects(600, 30, {**board, "dayCap": "1200"}), "a cap that is not a number is refused"
assert rejects(600, 30, "board"), "a fee sheet that is not a mapping is refused"
print("ok")
