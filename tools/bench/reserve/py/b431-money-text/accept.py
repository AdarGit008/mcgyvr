from solution import money_text

assert money_text(1234) == "12.34", "pounds and pence"
assert money_text(5) == "0.05", "under a pound keeps its nought"
assert money_text(100) == "1.00", "a whole pound shows two noughts"
assert money_text(0) == "0.00", "nothing at all"
assert money_text(99) == "0.99", "just under a pound"
assert money_text(1000) == "10.00", "ten pounds"
print("ok")
