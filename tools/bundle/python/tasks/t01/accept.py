import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

cases = [("aaabb", "a3b2"), ("", ""), ("a", "a1"), ("ab", "a1b1"),
         ("aabbbba", "a2b4a1"), ("zzzzz", "z5")]
for s, want in cases:
    got = solution.rle_encode(s)
    check(got == want, f"rle_encode({s!r}) = {got!r}, want {want!r}")
print("OK")
