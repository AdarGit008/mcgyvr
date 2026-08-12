from solution import code_hash


def rejects(code, buckets):
    try:
        code_hash(code, buckets)
    except Exception:
        return True
    return False


assert code_hash("a", 10) == 1, "a is one"
assert code_hash("z", 100) == 26, "z is twenty-six"
assert code_hash("ab", 10) == 3, "the letters add up"
assert code_hash("", 5) == 0, "no letters, no total"
assert code_hash("a1b", 10) == 3, "a digit adds nothing"
assert code_hash("AB", 10) == 3, "case is ignored"
assert rejects("a", 0), "no buckets is rejected"
print("ok")
