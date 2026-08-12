from solution import closing_sheet

assert closing_sheet("bolt:12;washer:4", "") == "bolt:12;washer:4", "no moves leaves the sheet"
assert closing_sheet("washer:4;bolt:12", "") == "bolt:12;washer:4", "entries come back sorted by name"
assert closing_sheet("", "") == "", "empty sheet and no moves"
assert closing_sheet("", "nail+25") == "nail:25", "receive onto an empty sheet"
assert closing_sheet("nail:5", "nail+7") == "nail:12", "receive adds to the count"
assert closing_sheet("nail:5;screw:9", "screw-4") == "nail:5;screw:5", "issue draws the count down"
assert closing_sheet("nail:5", "nail-5") == "", "an item drawn to zero is dropped"
assert closing_sheet("bolt:0", "") == "", "an opening zero count is dropped"
assert closing_sheet("nail:2;bolt:8", "nail+1;bolt-3;nail-3") == "bolt:5", "moves apply in order"


def rejects(opening, moves):
    try:
        closing_sheet(opening, moves)
    except Exception:
        return True
    return False


assert rejects(7, ""), "non-string sheet is rejected"
assert rejects("nail:5", 7), "non-string moves are rejected"
assert rejects("nail5", ""), "entry without a colon is rejected"
assert rejects("nail:05", ""), "leading zero count is rejected"
assert rejects("nail:5;nail:2", ""), "duplicate name is rejected"
assert rejects("nail:5", "nail*2"), "unknown move mark is rejected"
assert rejects("nail:5", "nail+0"), "zero quantity is rejected"
assert rejects("nail:5", "screw-1"), "issue of an absent item is rejected"
assert rejects("nail:5", "nail-6"), "overdrawn issue is rejected"
print("ok")
