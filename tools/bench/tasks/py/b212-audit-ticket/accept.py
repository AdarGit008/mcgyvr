from solution import audit_ticket


def rejects(value):
    try:
        audit_ticket(value)
    except Exception:
        return True
    return False


assert audit_ticket("AB-1234-3") == "ok", "a sound ticket passes"
assert audit_ticket("ZZ-0000-2") == "ok", "the heaviest letters with empty digits pass"
assert audit_ticket("AE-4000-0") == "ok", "a total ending in zero wants the digit zero"
assert audit_ticket("AB-1234-7") == "check", "a wrong check digit is named"
assert audit_ticket("ab-1234-3") == "shape", "small letters break the shape"
assert audit_ticket("AB-123-3") == "shape", "too few digits break the shape"
assert rejects(42), "a ticket that is not a string is rejected"
print("ok")
