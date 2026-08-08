from solution import plan_key_presses

PHONE = [" ", "", "ABC", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ"]
TINY = ["_", "", "AB", "CD", "EF", "", "", "", "", ""]


def rejects(text, layout):
    try:
        plan_key_presses(text, layout)
    except ValueError:
        return True
    return False


assert plan_key_presses("HELLO", PHONE) == "4433555.555666", "a repeated key is parted by a full stop"
assert plan_key_presses("MOON", PHONE) == "6.666.666.66", "four characters on one key"
assert plan_key_presses("H H", PHONE) == "44044", "a different key needs no separator"
assert plan_key_presses("Z", PHONE) == "9999", "the last character of a key"
assert plan_key_presses("S", PHONE) == "7777", "a four-character key"
assert plan_key_presses("BAD", TINY) == "22.233", "a layout of the caller's own"
assert plan_key_presses("_", TINY) == "0", "key 0 carries one character"
assert plan_key_presses("FEED", TINY) == "44.4.433", "three stretches on one key then another"

assert rejects("", PHONE), "empty text is refused"
assert rejects(9, PHONE), "text that is not a string is refused"
assert rejects("HI", PHONE[:9]), "nine keys are refused"
assert rejects("HI", "not a layout"), "a layout that is not a list is refused"
assert rejects(
    "HI", [" ", "", "ABC", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", 9]
), "a key that is not a string is refused"
assert rejects("HI!", PHONE), "a character on no key is refused"
assert rejects("G", TINY), "a smaller layout refuses what it never listed"
assert rejects(
    "A", [" ", "", "ABC", "DEA", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ"]
), "a character listed on two keys is refused"
assert rejects(
    "A", [" ", "", "ABA", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ"]
), "a character listed twice on one key is refused"
print("ok")
