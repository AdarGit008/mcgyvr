from solution import merge_sheet_marks


def rejects(value):
    try:
        merge_sheet_marks(value)
    except ValueError:
        return True
    return False


assert merge_sheet_marks(["3-7"]) == {"spec": "3-7", "sheets": 5}, "one span, already canonical"
assert merge_sheet_marks(["1 2 3"]) == {
    "spec": "1-3",
    "sheets": 3,
}, "lone sheets draw together into a run"
assert merge_sheet_marks([]) == {"spec": "", "sheets": 0}, "no readers hold nothing"
assert merge_sheet_marks(["!5"]) == {
    "spec": "",
    "sheets": 0,
}, "striking what was never gathered holds nothing"
assert merge_sheet_marks(["1-9 !1-9"]) == {
    "spec": "",
    "sheets": 0,
}, "a strike may empty the holding"
assert merge_sheet_marks(["1-5 !3"]) == {
    "spec": "1-2 4-5",
    "sheets": 4,
}, "a strike through the middle leaves two runs"
assert merge_sheet_marks(["1-5", "!2-4"]) == {
    "spec": "1 5",
    "sheets": 2,
}, "a later reader strikes what an earlier one gathered"
assert merge_sheet_marks(["1-3 5-7", "4"]) == {
    "spec": "1-7",
    "sheets": 7,
}, "a gather between two runs welds them into one"
assert merge_sheet_marks(["10-12 !11 11"]) == {
    "spec": "10-12",
    "sheets": 3,
}, "a gather may put back what a strike took away"
assert merge_sheet_marks(["9999", "1"]) == {
    "spec": "1 9999",
    "sheets": 2,
}, "the ends of the run of sheets"
assert merge_sheet_marks(["5", "5"]) == {
    "spec": "5",
    "sheets": 1,
}, "gathering one sheet twice holds it once"
assert merge_sheet_marks(["2-4 6", "!3 8-9", "!9"]) == {
    "spec": "2 4 6 8",
    "sheets": 4,
}, "three readers over one holding"
assert merge_sheet_marks(["4-4"]) == {
    "spec": "4",
    "sheets": 1,
}, "a span of one renders as a lone figure"

assert rejects("1-2"), "an argument that is not a list is refused"
assert rejects([5]), "a mark that is not a string is refused"
assert rejects([""]), "an empty mark is refused"
assert rejects([" 1"]), "a leading blank is refused"
assert rejects(["1 "]), "a trailing blank is refused"
assert rejects(["1  2"]), "two blanks running together are refused"
assert rejects(["1--2"]), "a doubled hyphen is refused"
assert rejects(["!"]), "a bare exclamation mark is refused"
assert rejects(["!!1"]), "a doubled exclamation mark is refused"
assert rejects(["1!2"]), "an exclamation mark inside a segment is refused"
assert rejects(["01"]), "a leading nought is refused"
assert rejects(["0"]), "a sheet of nought is refused"
assert rejects(["10000"]), "a sheet past the last is refused"
assert rejects(["7-3"]), "a backwards span is refused"
assert rejects(["!7-3"]), "a backwards strike is refused"
print("ok")
