from solution import share_out


def rejects(amount, parts):
    try:
        share_out(amount, parts)
    except Exception:
        return True
    return False


assert share_out(10, 3) == [4, 3, 3], "the leftover goes to the earliest part"
assert share_out(9, 3) == [3, 3, 3], "the amount breaks evenly"
assert share_out(2, 5) == [1, 1, 0, 0, 0], "fewer to hand out than parts"
assert share_out(7, 1) == [7], "a single part takes it all"
assert share_out(0, 2) == [0, 0], "an amount of nothing"
assert rejects(5, 0), "a count of parts below one is rejected"
print("ok")
