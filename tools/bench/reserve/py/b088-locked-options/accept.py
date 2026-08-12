from solution import settle_options

assert settle_options({"mode": "dev"}, {}, {}, []) == {"mode": "dev"}, "defaults pass through"
assert settle_options({"retries": "1"}, {"retries": "4"}, {}, []) == {"retries": "4"}, (
    "the file beats defaults"
)
assert settle_options({"level": "a"}, {"level": "b"}, {"level": "c"}, []) == {"level": "c"}, (
    "a flag beats the file"
)
assert settle_options({"a": "1"}, {"b": "2"}, {"c": "3"}, []) == {
    "a": "1",
    "b": "2",
    "c": "3",
}, "disjoint keys all survive"
assert settle_options({"port": "80"}, {"port": "8080"}, {}, ["port"]) == {"port": "8080"}, (
    "the file may still set a locked key"
)
assert settle_options({"port": "80"}, {}, {"host": "far"}, ["port"]) == {
    "port": "80",
    "host": "far",
}, "a lock only guards its own key"
assert settle_options({}, {}, {}, []) == {}, "nothing in, nothing out"


def rejects(*args):
    try:
        settle_options(*args)
    except Exception:
        return True
    return False


assert rejects({}, {}, {"port": "1"}, ["port"]), "flag on a locked key is rejected"
assert rejects(None, {}, {}, []), "a missing source is rejected"
assert rejects({}, ["x"], {}, []), "a list source is rejected"
assert rejects({"a": 5}, {}, {}, []), "a numeric value is rejected"
assert rejects({}, {}, {}, [7]), "a non-string lock is rejected"
print("ok")
