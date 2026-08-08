from solution import corvid_render

assert corvid_render(0) == "x", "nothing is the lone x"
assert corvid_render(1) == "y", "plus one"
assert corvid_render(2) == "z", "plus two"
assert corvid_render(3) == "yv", "three leans back"
assert corvid_render(4) == "yw", "four leans back"
assert corvid_render(5) == "yx", "five needs the middle mark"
assert corvid_render(6) == "yy", "six"
assert corvid_render(12) == "zz", "twelve"
assert corvid_render(13) == "yvv", "thirteen"
assert corvid_render(62) == "zzz", "the largest three-mark tally"
assert corvid_render(63) == "yvvv", "one past it needs four marks"
assert corvid_render(100) == "ywxx", "a hundred"
assert corvid_render(-1) == "w", "minus one"
assert corvid_render(-2) == "v", "minus two"
assert corvid_render(-3) == "wz", "minus three"
assert corvid_render(-4) == "wy", "minus four"
assert corvid_render(-13) == "wzz", "minus thirteen"
assert corvid_render(-100) == "wyxx", "minus a hundred mirrors the mark leans"
assert corvid_render(-63) == "wzzz", "minus sixty-three"


def rejects(value):
    try:
        corvid_render(value)
    except ValueError:
        return True
    return False


assert rejects(2.5), "fraction rejected"
assert rejects("12"), "text rejected"
assert rejects(True), "true-or-false rejected"
assert rejects(float("inf")), "unbounded rejected"
assert rejects(float("nan")), "not-a-number rejected"
assert rejects(None), "nothing at all rejected"
print("ok")
