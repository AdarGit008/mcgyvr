from solution import diff_paths

assert diff_paths({}, {}) == [], "identical empty trees differ nowhere"
assert diff_paths({"theme": "mono"}, {"theme": "mono"}) == [], "an unchanged leaf is not reported"
assert diff_paths({"theme": "mono"}, {"theme": "sepia"}) == ["theme"], "a changed leaf reports its key"
assert diff_paths({"old": "1"}, {"fresh": "2"}) == ["fresh", "old"], "keys on only one side are reported, sorted"
assert diff_paths({"display": {"theme": "mono", "scale": "2"}}, {"display": {"theme": "sepia", "scale": "2"}}) == ["display/theme"], "a change inside matching sections joins keys with slashes"
assert diff_paths({"sound": "on"}, {"sound": {"alarm": "on"}}) == ["sound"], "a leaf facing a section reports the path itself"
assert diff_paths({"b": {"z": "1"}, "a": "x"}, {"b": {"z": "2"}, "a": "y"}) == ["a", "b/z"], "reported paths come out sorted across levels"


def rejects(before, after):
    try:
        diff_paths(before, after)
    except Exception:
        return True
    return False


assert rejects("flat", {}), "a before that is not a mapping is rejected"
assert rejects({}, 7), "an after that is not a mapping is rejected"
assert rejects({"scale": 2}, {"scale": 2}), "a numeric leaf is rejected even when both sides match"
assert rejects({}, {"dark": True}), "a boolean leaf is rejected"
print("ok")
