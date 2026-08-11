from solution import check_digit


def rejects(value):
    try:
        check_digit(value)
    except Exception:
        return True
    return False


assert check_digit("123") == 4, "six needs four more"
assert check_digit("0") == 0, "zero is already a multiple"
assert check_digit("55") == 0, "ten is already a multiple"
assert check_digit("999") == 3, "twenty-seven needs three"
assert check_digit("") == 0, "no digits need nothing"
assert rejects("12a"), "a letter is rejected"
print("ok")
