from solution import apply_charges

quotas = {"api": [10, 4], "sms": [5, 5]}

assert apply_charges(quotas, [["c1", "api", 4], ["c2", "api", 5], ["c3", "mail", 1], ["c4", "api", 4], ["c5", "api", 3], ["c6", "sms", 5]]) == {"left": {"api": 2, "sms": 0}, "refused": [["c2", "single"], ["c3", "unknown"], ["c5", "cap"]]}, "each refusal names the first test the charge failed"
assert apply_charges(quotas, []) == {"left": {"api": 10, "sms": 5}, "refused": []}, "with no charges every allowance still stands"
assert apply_charges({"api": [3, 3]}, [["c1", "api", 3]]) == {"left": {"api": 0}, "refused": []}, "a charge that empties the bucket exactly is accepted"
assert apply_charges({"api": [2, 9]}, [["c1", "api", 5]]) == {"left": {"api": 2}, "refused": [["c1", "cap"]]}, "a charge under the single ceiling can still fail the cap"
assert apply_charges({"api": [2, 9]}, [["z1", "post", 1]]) == {"left": {"api": 2}, "refused": [["z1", "unknown"]]}, "an unknown bucket spends nothing"


def rejects(*args):
    try:
        apply_charges(*args)
    except Exception:
        return True
    return False


assert rejects(quotas, [["c1", "api", 0]]), "an amount that is not positive is rejected"
print("ok")
