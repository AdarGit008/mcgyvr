from solution import short_num

assert short_num(1200) == "1.2k", "a thousand takes k"
assert short_num(999) == "999", "below a thousand is written out"
assert short_num(1000) == "1.0k", "exactly a thousand"
assert short_num(1500000) == "1.5m", "a million takes m"
assert short_num(0) == "0", "nothing is written out"
assert short_num(1999) == "1.9k", "the decimal rounds down"
print("ok")
