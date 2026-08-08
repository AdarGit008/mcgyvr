from solution import shift_front_codes

LETTERS = "abcdefghijklmnopqrstuvwxyz"

assert shift_front_codes("abcd", "dab") == [3, 1, 2], "the stated dab example"
assert shift_front_codes(LETTERS, "banana") == [
    1,
    1,
    13,
    1,
    1,
    1,
], "an alternating message settles into ones"
assert shift_front_codes(LETTERS, "bananaaa") == [
    1,
    1,
    13,
    1,
    1,
    1,
    0,
    0,
], "a repeat of the head reads zero"
assert shift_front_codes("abc", "") == [], "an empty message"
assert shift_front_codes("abc", "aaa") == [0, 0, 0], "the head stays the head"
assert shift_front_codes("abc", "cba") == [
    2,
    2,
    2,
], "each character walks in from the tail"
assert shift_front_codes("xyz", "zzx") == [
    2,
    0,
    1,
], "the row keeps its order behind the head"
assert shift_front_codes(".-#", "#.-#") == [
    2,
    1,
    2,
    2,
], "the alphabet need not be letters"


def rejects(alphabet, message):
    try:
        shift_front_codes(alphabet, message)
    except ValueError:
        return True
    return False


assert rejects(5, "ab"), "an alphabet that is not a string is thrown out"
assert rejects("", ""), "an empty alphabet is thrown out"
assert rejects("abca", "a"), "a repeated alphabet character is thrown out"
assert rejects("abc", ["a"]), "a message that is not a string is thrown out"
assert rejects("abc", "ad"), "a character outside the alphabet is thrown out"
print("ok")
