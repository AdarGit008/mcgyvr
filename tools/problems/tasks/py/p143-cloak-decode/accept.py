from solution import cloak_decode

assert cloak_decode("orbit", "roi") == "bad", "worked example"
assert cloak_decode("orbit", "qtbpts jtqqoct") == "secret message", "phrase with space"
assert cloak_decode("velvet", "osfar dvpemp") == "quiet harbor", "keyword with repeats"
assert cloak_decode("gadget", "ztaqg lukt") == "zebra mule", "another keyword"
assert cloak_decode("zed", "zebra") == "abesd", "short keyword"
assert cloak_decode("ba", "ba") == "ab", "two-letter keyword swaps a and b"


def rejects(keyword, text):
    try:
        cloak_decode(keyword, text)
    except ValueError:
        return True
    return False


assert rejects("", "roi"), "empty keyword is rejected"
assert rejects("Bad", "roi"), "uppercase keyword is rejected"
assert rejects("orbit", "r2"), "digit in text is rejected"
assert rejects("orbit", 7), "non-string text is rejected"
print("ok")
