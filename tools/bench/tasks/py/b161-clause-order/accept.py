from solution import clause_order

assert clause_order("3.2", "3.2") == 0, "identical marks are equal"
assert clause_order("1.9", "1.10") == -1, "numbers compare numerically, not as text"
assert clause_order("2.1", "1.9") == 1, "a later front number wins"
assert clause_order("3.2", "3.2.1") == -1, "a mark that extends another comes after it"
assert clause_order("4.1.1", "4.1") == 1, "the extended mark is the later one"
assert clause_order("7", "11") == -1, "single numbers compare numerically"
assert clause_order("10.0", "9.9") == 1, "the front number outranks the rest"


def rejects(*args):
    try:
        clause_order(*args)
    except Exception:
        return True
    return False


assert rejects(3.2, "1"), "a non-string mark is rejected"
assert rejects("", "1"), "an empty mark is rejected"
assert rejects("1..2", "1"), "an empty number from a stray dot is rejected"
assert rejects("1.02", "1"), "a leading zero is rejected"
assert rejects("1.2a", "1"), "a stray character is rejected"
print("ok")
