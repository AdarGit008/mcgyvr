from solution import token_fetch, token_save

vault = {}
token_save(vault, "auth", "abc", 10, 5)
assert vault == {"auth": ["abc", 15]}, "save records the value and its expiry tick"
assert token_fetch(vault, "auth", 14) == "abc", "the last tick before expiry still hits"
assert token_fetch(vault, "auth", 15) is None, "the expiry tick itself misses"
assert vault == {}, "an expired entry is removed by the fetch"
assert token_fetch({}, "ghost", 0) is None, "a name never held misses"

second = {}
token_save(second, "job", "one", 0, 10)
token_save(second, "job", "two", 5, 3)
assert token_fetch(second, "job", 7) == "two", "saving again replaces value and expiry"


def rejects(vault, name, value, now, ttl):
    try:
        token_save(vault, name, value, now, ttl)
    except ValueError:
        return True
    return False


assert rejects({}, "k", "v", 0, 0), "a zero ttl is rejected"
assert rejects({}, "k", "v", 1.5, 3), "a fractional now is rejected"
assert rejects({}, "", "v", 0, 3), "an empty name is rejected"
print("ok")
