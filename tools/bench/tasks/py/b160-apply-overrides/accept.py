from solution import apply_overrides

assert apply_overrides({"retries": "3"}, []) == {"retries": "3"}, "no overrides returns the base settings"
assert apply_overrides({"host": "a", "port": "80"}, ["port=8080"]) == {"host": "a", "port": "8080"}, "an override replaces one setting"
assert apply_overrides({"port": "80"}, ["port=1", "port=2"]) == {"port": "2"}, "a later override beats an earlier one"
assert apply_overrides({"mode": "fast"}, ["mode="]) == {"mode": ""}, "an empty value is allowed"
assert apply_overrides({"rule": "x"}, ["rule=a=b"]) == {"rule": "a=b"}, "only the first equals sign splits"
base = {"port": "80"}
apply_overrides(base, ["port=1"])
assert base == {"port": "80"}, "base itself is left untouched"


def rejects(*args):
    try:
        apply_overrides(*args)
    except Exception:
        return True
    return False


assert rejects({"a": "1"}, "a=2"), "a non-list overrides argument is rejected"
assert rejects({"a": "1"}, [7]), "a non-string override is rejected"
assert rejects({"port": "80"}, ["port"]), "an override without an equals sign is rejected"
assert rejects({"port": "80"}, ["=1"]), "an empty override name is rejected"
assert rejects({"port": "80"}, ["ghost=1"]), "an unknown setting name is rejected"
print("ok")
