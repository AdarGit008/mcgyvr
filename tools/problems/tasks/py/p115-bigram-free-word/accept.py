from solution import smallest_free_word

assert smallest_free_word(3, 2, []) == "aaa", "no bans means all a"
assert smallest_free_word(3, 2, ["aa"]) == "aba", "aa banned forces alternation"
assert smallest_free_word(2, 2, ["aa", "ab"]) == "ba", "initial a dead-ends"
assert smallest_free_word(4, 2, ["aa", "bb"]) == "abab", "strict alternation"
assert smallest_free_word(1, 2, ["aa", "ab", "ba", "bb"]) == "a", "length one"
assert smallest_free_word(5, 3, ["aa", "ab", "ac"]) == "bbbba", "a only at the end"
assert smallest_free_word(2, 3, ["aa", "ab"]) == "ac", "third letter rescues a"


def rejects(*args):
    try:
        smallest_free_word(*args)
    except ValueError:
        return True
    return False


assert rejects(2, 1, ["aa"]), "impossible instance"
assert rejects(0, 2, []), "zero length"
assert rejects(13, 2, []), "length beyond cap"
assert rejects(3, 7, []), "alphabet beyond cap"
assert rejects(3, 2, ["abc"]), "three-letter ban"
assert rejects(3, 2, ["az"]), "ban outside alphabet"
assert rejects(3, 2, "aa"), "banned not a list"
print("ok")
