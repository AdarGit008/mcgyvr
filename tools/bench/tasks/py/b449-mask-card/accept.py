from solution import last_four, mask_card

assert last_four("123456") == "3456", "the last four"
assert last_four("12") == "12", "a short number is all of it"
assert mask_card("123456") == "**3456", "two characters hidden"
assert mask_card("1234") == "1234", "nothing to hide"
assert mask_card("") == "", "an empty number"
assert mask_card("123456789") == "*****6789", "a longer number"
print("ok")
