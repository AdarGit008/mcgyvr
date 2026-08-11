from solution import code_valid


def rejects(code, length):
    try:
        code_valid(code, length)
    except Exception:
        return True
    return False


assert code_valid("AB12", 4) is True, "the right length and charset"
assert code_valid("ab12", 4) is False, "small letters are not allowed"
assert code_valid("AB1", 4) is False, "too short"
assert code_valid("AB-2", 4) is False, "a dash is not allowed"
assert code_valid("", 1) is False, "an empty code is never the right length"
assert rejects("A", 0), "a length of zero is rejected"
print("ok")
