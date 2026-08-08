from solution import normalize_hostname

assert normalize_hostname("Example.COM") == "example.com", "lowercased"
assert normalize_hostname("example.com.") == "example.com", "trailing dot drops"
assert normalize_hostname("a.b-c.d0") == "a.b-c.d0", "hyphens and digits pass"
assert normalize_hostname("X") == "x", "single label"
assert (
    normalize_hostname("a" * 63 + ".io") == "a" * 63 + ".io"
), "63-character label is the maximum"


def rejects(value):
    try:
        normalize_hostname(value)
    except ValueError:
        return True
    return False


assert rejects("a" * 64 + ".io"), "64-character label is rejected"
assert rejects(("a" * 63 + ".") * 4), "name longer than 253 characters is rejected"
assert rejects(""), "empty name is rejected"
assert rejects("a..b"), "empty label is rejected"
assert rejects("a.."), "two trailing dots are rejected"
assert rejects("-a.com"), "leading hyphen is rejected"
assert rejects("a-.com"), "trailing hyphen is rejected"
assert rejects("a_b.com"), "underscore is rejected"
assert rejects("exa mple.com"), "space is rejected"
assert rejects(9), "non-string is rejected"
print("ok")
