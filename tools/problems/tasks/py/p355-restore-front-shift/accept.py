from solution import restore_front_shift

LETTERS = "abcdefghijklmnopqrstuvwxyz"

assert restore_front_shift("abcd", [3, 1, 2]) == "dab", "the stated dab example"
assert (
    restore_front_shift(LETTERS, [1, 1, 13, 1, 1, 1]) == "banana"
), "a long ring rearranged six times"
assert (
    restore_front_shift(LETTERS, [1, 1, 13, 1, 1, 1, 0, 0]) == "bananaaa"
), "slot zero repeats the last character"
assert restore_front_shift("abc", []) == "", "an empty code list"
assert restore_front_shift("abc", [0, 0, 0]) == "aaa", "the front stays put"
assert restore_front_shift("abc", [2, 2, 2]) == "cba", "the tail slot walks forward"
assert (
    restore_front_shift("xyz", [2, 0, 1]) == "zzx"
), "the ring keeps its order behind the front"
assert (
    restore_front_shift(".-#", [2, 1, 2, 2]) == "#.-#"
), "the alphabet need not be letters"


def rejects(alphabet, codes):
    try:
        restore_front_shift(alphabet, codes)
    except ValueError:
        return True
    return False


assert rejects(5, [0]), "an alphabet that is not a string is thrown out"
assert rejects("", []), "an empty alphabet is thrown out"
assert rejects("abca", [0]), "a repeated alphabet character is thrown out"
assert rejects("abc", "0"), "codes that are not a list are thrown out"
assert rejects("abc", [0, 1.5]), "a code that is not whole is thrown out"
assert rejects("abc", [3]), "a code naming no slot is thrown out"
print("ok")
