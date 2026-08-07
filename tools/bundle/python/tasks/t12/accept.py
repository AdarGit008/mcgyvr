import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

d = {"a": 1, "b": 5, "c": 2, "d": 9}
out = solution.drop_small(d, 3)
check(out is d, "must return the same dict object (in-place)")
check(d == {"b": 5, "d": 9}, f"drop_small result wrong: {d}")

d2 = {"x": 10}
out2 = solution.drop_small(d2, 3)
check(out2 is d2 and d2 == {"x": 10}, "nothing to drop should be a no-op")

d3 = {}
check(solution.drop_small(d3, 1) is d3, "empty dict should be a no-op")
print("OK")
