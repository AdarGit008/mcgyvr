from solution import score_scale

assert score_scale(5, 10, 100) == 50, "half of one total is half of another"
assert score_scale(10, 10, 100) == 100, "full marks stay full"
assert score_scale(0, 10, 100) == 0, "no marks stay none"
assert score_scale(11, 10, 100) == 100, "a mark over the total is held back"
assert score_scale(5, 0, 100) == 0, "nothing to scale from"
assert score_scale(1, 3, 10) == 3, "rounded down"
print("ok")
