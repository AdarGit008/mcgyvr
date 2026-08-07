import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

cases = [("a b c", "c b a"), ("hello", "hello"), ("", ""),
         ("one two", "two one"), ("w x y z", "z y x w")]
for arg, want in cases:
    got = solution.reverse_words(arg)
    check(got == want, f"reverse_words({arg!r}) = {got!r}, want {want!r}")
print("OK")
