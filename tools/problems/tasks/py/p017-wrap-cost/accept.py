from solution import wrap_cost

assert wrap_cost(["ab", "cd"], 5) == 0, "a perfect single line costs nothing"
assert wrap_cost(["ab", "cd"], 4) == 8, "forced onto two lines"
assert wrap_cost(["a", "b", "c"], 3) == 4, "pair one line, leave one word"
assert wrap_cost(["aaa", "bb", "cc", "ddddd"], 6) == 11, (
    "greedy packing gives 17 here; the best split gives 11"
)
assert wrap_cost(["hello"], 5) == 0, "one word, exact fit"
assert wrap_cost(["hi"], 5) == 9, "one short word pays its slack"
assert wrap_cost(["a", "bb", "c"], 6) == 0, "all words on one full line"


def rejects(words, width):
    try:
        wrap_cost(words, width)
    except ValueError:
        return True
    return False


assert rejects(["toolong"], 3), "an oversized word is rejected"
assert rejects(["a"], 0), "zero width rejected"
assert rejects(["a"], 2.5), "fractional width rejected"
assert rejects([], 5), "empty word list rejected"
assert rejects(["a", ""], 5), "empty word rejected"
print("ok")
