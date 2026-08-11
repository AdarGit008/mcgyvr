from solution import good_codes

assert good_codes(["12", "14"]) == ["12"], "only the even total is kept"
assert good_codes(["a1b2"]) == ["a1b2"], "anything not a figure is passed over"
assert good_codes(["9", "33"]) == ["9", "33"], "two codes that both divide evenly"
assert good_codes(["00"]) == ["00"], "a total of nothing divides evenly"
assert good_codes(["7"]) == [], "no code divides evenly"
assert good_codes([]) == [], "no codes at all"
print("ok")
