from solution import run_decode

assert run_decode("A3B1") == "AAAB", "two runs written out"
assert run_decode("A1") == "A", "a run of one"
assert run_decode("") == "", "nothing to decode"
assert run_decode("X10") == "XXXXXXXXXX", "a count of two digits"
assert run_decode("A0B2") == "BB", "a run of none disappears"
assert run_decode("Z2") == "ZZ", "a single run"
print("ok")
