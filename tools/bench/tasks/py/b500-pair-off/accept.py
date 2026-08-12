from solution import pair_off

assert pair_off(["a", "a"]) == [], "a neighbouring pair goes"
assert pair_off(["a", "b", "b", "a"]) == [], "the outer pair meets once the inner goes"
assert pair_off(["a", "a", "b"]) == ["b"], "one pair goes and a mark is left"
assert pair_off(["a", "b", "a"]) == ["a", "b", "a"], "no two of a kind stand together"
assert pair_off(["a"]) == ["a"], "a lone mark"
assert pair_off([]) == [], "no marks at all"
print("ok")
