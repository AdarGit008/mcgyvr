from solution import mask_account

assert mask_account("12345678", 4) == "****5678", "plain digits"
assert mask_account("1234-5678-9012", 4) == "****-****-9012", "hyphen groups"
assert mask_account("1234 5678 9012 3456", 4) == "**** **** **** 3456", "space groups"
assert mask_account("007", 3) == "007", "exactly keep digits is unchanged"
assert mask_account("9-87", 1) == "*-*7", "keep of one"


def rejects(*args):
    try:
        mask_account(*args)
    except ValueError:
        return True
    return False


assert rejects(42, 4), "non-string account is rejected"
assert rejects("", 4), "empty account is rejected"
assert rejects("12a4", 2), "illegal character is rejected"
assert rejects("-123", 2), "leading separator is rejected"
assert rejects("12--34", 2), "adjacent separators are rejected"
assert rejects("1234", 0), "keep below one is rejected"
assert rejects("123", 4), "fewer digits than keep is rejected"
print("ok")
