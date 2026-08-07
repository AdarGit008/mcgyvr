import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

check(solution.tag_item("a") == ["a"], "first default call should be ['a']")
check(solution.tag_item("b") == ["b"],
      "second default call should be ['b'] — default list must not accumulate")

mine = ["x"]
out = solution.tag_item("y", mine)
check(out is mine, "provided list must be returned (same object)")
check(mine == ["x", "y"], f"provided list must be appended in place, got {mine}")
print("OK")
