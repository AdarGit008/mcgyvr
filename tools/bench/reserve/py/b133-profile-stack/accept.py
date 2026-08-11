from solution import merge_layers, resolve_profile

assert merge_layers({"a": 1, "sub": {"x": 1, "y": 2}}, {"sub": {"y": 3}, "b": 4}) == {
    "a": 1,
    "sub": {"x": 1, "y": 3},
    "b": 4,
}, "nested mappings merge key by key"
assert merge_layers({"k": 1}, {"k": {"deep": 2}}) == {"k": {"deep": 2}}, "a mapping replaces a scalar"
assert merge_layers({"k": {"deep": 2}}, {"k": 0}) == {"k": 0}, "a scalar replaces a mapping"
pristine = {"keep": {"safe": 1}}
merge_layers(pristine, {"keep": {"safe": 2}})
assert pristine == {"keep": {"safe": 1}}, "the base is never mutated"

assert resolve_profile("solo", {"solo": {"settings": {"tone": "calm"}}}) == {
    "tone": "calm"
}, "a profile with no parents is its own settings"
assert resolve_profile("bare", {"bare": {}}) == {}, "no settings resolves empty"
catalog = {
    "base": {"settings": {"net": {"host": "hub.local", "port": 90}, "retries": 2}},
    "edge": {"extends": ["base"], "settings": {"net": {"port": 9090}}},
}
assert resolve_profile("edge", catalog) == {
    "net": {"host": "hub.local", "port": 9090},
    "retries": 2,
}, "a child deep-overrides its parent"
pair = {
    "left": {"settings": {"mode": "dry", "size": 1}},
    "right": {"settings": {"mode": "wet"}},
    "both": {"extends": ["left", "right"]},
}
assert resolve_profile("both", pair) == {"mode": "wet", "size": 1}, "a later parent wins"
chain = {
    "root": {"settings": {"depth": 0, "tag": "r"}},
    "mid": {"extends": ["root"], "settings": {"depth": 1}},
    "leaf": {"extends": ["mid"], "settings": {"tip": True}},
}
assert resolve_profile("leaf", chain) == {
    "depth": 1,
    "tag": "r",
    "tip": True,
}, "a chain resolves through every ancestor"
diamond = {
    "core": {"settings": {"seed": 1, "side": "none"}},
    "west": {"extends": ["core"], "settings": {"side": "w"}},
    "east": {"extends": ["core"], "settings": {"side": "e"}},
    "rim": {"extends": ["west", "east"]},
}
assert resolve_profile("rim", diamond) == {"seed": 1, "side": "e"}, "a diamond is not a cycle"


def rejects(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


assert rejects(merge_layers, 5, {}), "non-mapping base is rejected"
assert rejects(resolve_profile, "ghost", {}), "unknown profile is rejected"
assert rejects(resolve_profile, "a", {"a": {"extends": ["b"]}}), "unknown parent is rejected"
assert rejects(resolve_profile, "a", {"a": {"extends": ["a"]}}), "self cycle is rejected"
assert rejects(
    resolve_profile, "a", {"a": {"extends": ["b"]}, "b": {"extends": ["a"]}}
), "mutual cycle is rejected"
assert rejects(resolve_profile, "a", {"a": {"extends": "b"}}), "non-list extends is rejected"
assert rejects(resolve_profile, "a", {"a": {"extends": [5]}}), "non-string parent is rejected"
assert rejects(resolve_profile, "a", {"a": {"settings": 3}}), "non-mapping settings is rejected"
assert rejects(resolve_profile, "a", {"a": "nope"}), "non-mapping profile is rejected"
print("ok")
