from solution import gapped_match

assert gapped_match("abc", "abc", 0) == True, "exact text matches with gap 0"
assert gapped_match("abc", "axbxc", 1) == True, "one skip between letters"
assert gapped_match("abc", "axbxc", 0) == False, "gap 0 forbids those skips"
assert gapped_match("abc", "abxabc", 0) == True, (
    "the earliest start fails but a later one works"
)
assert gapped_match("aab", "aaxab", 0) == False, "no placement satisfies gap 0 here"
assert gapped_match("aab", "aaxab", 1) == True, "gap 1 lets the second a re-anchor"
assert gapped_match("zz", "zaz", 0) == False, "adjacent needed, one apart given"
assert gapped_match("zz", "zaz", 1) == True, "one apart allowed by gap 1"
assert gapped_match("a", "xxxa", 0) == True, "leading characters are free"
assert gapped_match("aba", "xxabya", 5) == True, "generous gap, late start"
assert gapped_match("abcd", "abc", 3) == False, "needle longer than haystack"


def rejects(needle, haystack, gap):
    try:
        gapped_match(needle, haystack, gap)
    except ValueError:
        return True
    return False


assert rejects("", "abc", 1), "empty needle rejected"
assert rejects("a", "abc", -1), "negative gap rejected"
assert rejects("a", "abc", 1.5), "fractional gap rejected"
print("ok")
