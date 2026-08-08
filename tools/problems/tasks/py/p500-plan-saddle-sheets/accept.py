from solution import plan_saddle_sheets

assert plan_saddle_sheets(8, "left") == [
    "1 front 8 1",
    "1 back 2 7",
    "2 front 6 3",
    "2 back 4 5",
], "eight pages fill two sheets exactly"

assert plan_saddle_sheets(4, "left") == [
    "1 front 4 1",
    "1 back 2 3",
], "four pages fill one sheet"

assert plan_saddle_sheets(12, "left") == [
    "1 front 12 1",
    "1 back 2 11",
    "2 front 10 3",
    "2 back 4 9",
    "3 front 8 5",
    "3 back 6 7",
], "twelve pages fill three sheets"

assert plan_saddle_sheets(5, "left") == [
    "1 front blank 1",
    "1 back 2 blank",
    "2 front blank 3",
    "2 back 4 5",
], "five pages pad out to eight"

assert plan_saddle_sheets(6, "left") == [
    "1 front blank 1",
    "1 back 2 blank",
    "2 front 6 3",
    "2 back 4 5",
], "six pages pad out with two blanks"

assert plan_saddle_sheets(1, "left") == [
    "1 front blank 1",
    "1 back blank blank",
], "a single page leaves three blanks"

assert plan_saddle_sheets(8, "right") == [
    "1 front 1 8",
    "1 back 7 2",
    "2 front 3 6",
    "2 back 5 4",
], "a right binding turns every side about"

assert plan_saddle_sheets(2, "right") == [
    "1 front 1 blank",
    "1 back blank 2",
], "a right binding on a padded sheet"


def rejects(*args):
    try:
        plan_saddle_sheets(*args)
    except ValueError:
        return True
    return False


assert rejects(0, "left"), "no pages at all is refused"
assert rejects(4001, "left"), "beyond four thousand is refused"
assert rejects(2.5, "left"), "a fractional page count is refused"
assert rejects("8", "left"), "a page count that is text is refused"
assert rejects(8, "middle"), "an unknown binding is refused"
assert rejects(8, 5), "a binding that is not a word is refused"
print("ok")
