from solution import justify_spacing

assert justify_spacing(10, [["a", "bb", "c"], ["done"]]) == [
    [3, 3],
    [],
], "a body line spreads its spare width evenly"
assert justify_spacing(11, [["ab", "cd", "ef"], ["end"]]) == [
    [3, 2],
    [],
], "the leftmost gap takes the extra space"
assert justify_spacing(8, [["to", "go", "up"], ["x"]]) == [
    [1, 1],
    [],
], "an exactly fitting body line keeps single spaces"
assert justify_spacing(20, [["all", "done", "here"]]) == [
    [1, 1]
], "a one-line paragraph is its own last line, set ragged"
assert justify_spacing(9, [["stretch"], ["on"]]) == [
    [],
    [],
], "a lone word on a body line yields no gaps"
assert justify_spacing(12, [["fill", "me", "up"], ["the", "end"]]) == [
    [2, 2],
    [1],
], "the last line keeps single spaces however wide the column"
assert justify_spacing(12, [["a", "b", "c", "d"], ["e"]]) == [
    [3, 3, 2],
    [],
], "extra space lands on the leftmost of three gaps"


def rejects(width, lines):
    try:
        justify_spacing(width, lines)
    except Exception:
        return True
    return False


assert rejects(0, [["a"]]), "a zero width is rejected"
assert rejects(2.5, [["a"]]), "a fractional width is rejected"
assert rejects(5, []), "an empty paragraph is rejected"
assert rejects(5, [[]]), "an empty line is rejected"
assert rejects(5, [["", "a"]]), "an empty word is rejected"
assert rejects(9, [["a b"]]), "a word with a space is rejected"
assert rejects(3, [["abc", "d"], ["x"]]), "an overrun body line is rejected"
assert rejects(3, [["abcd"]]), "an overrun last line is rejected"
print("ok")
